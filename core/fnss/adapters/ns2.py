"""Adapter for ns-2.

This module contains the code for converting an FNSS topology object into a Tcl
script to deploy such topology into ns-2.
"""
from warnings import warn

from fnss.units import time_units, capacity_units
from fnss.netconfig.nodeconfig import get_stack, \
                                      get_application_names, \
                                      get_application_properties


__all__ = [
    'to_ns2',
    'validate_ns2_stacks'
          ]


# Template text rendered by the template engine
__TEMPLATE = r"""# Code generated by Fast Network Simulator Setup (FNSS)
<%
from fnss.units import time_units, capacity_units
from fnss.netconfig.nodeconfig import get_stack, \
                                      get_application_names, \
                                      get_application_properties

# Convert capacity in Mb
capacity_norm = capacity_units[topology.graph['capacity_unit']] / 1000000.0
# Convert delay it in ms
if set_delays: delay_norm = time_units[topology.graph['delay_unit']]
%>
# Create a simulator object
set ns [new Simulator]

# Create nodes
% for node in topology.nodes_iter():
set n${str(node)} [$ns node]
% endfor

# Create all links
set qtype DropTail
## if topology is undirected, create duplex links, otherwise simplex links
% if topology.is_directed():
    % for u, v in topology.edges_iter():
<% delay = "0" if not set_delays else str(topology.edge[u][v]['delay'] * delay_norm) %>\
${"$ns simplex-link $n%s $n%s %sMb %sms $qtype" % (str(u), str(v), str(topology.edge[u][v]['capacity'] * capacity_norm), delay)}
    % endfor
% else:
    % for u, v in topology.edges_iter():
<% delay = "0" if not set_delays else str(topology.edge[u][v]['delay'] * delay_norm) %>\
${"$ns duplex-link $n%s $n%s %sMb %sms $qtype" % (str(u), str(v), str(topology.edge[u][v]['capacity'] * capacity_norm), delay)}
    % endfor
%endif

% if set_weights:
# Set link weights
    % for u, v in topology.edges_iter():
${"$ns cost $n%s $n%s %s" % (str(u), str(v), str(topology.edge[u][v]['weight']))}
        % if not topology.is_directed():
${"$ns cost $n%s $n%s %s" % (str(v), str(u), str(topology.edge[v][u]['weight']))}
        % endif
    % endfor
% endif

% if set_buffers:
# Set queue sizes
    % for u, v in topology.edges_iter():
${"$ns queue-limit $n%s $n%s %s" % (str(u), str(v), str(topology.edge[u][v]['buffer']))}
        % if not topology.is_directed():
${"$ns queue-limit $n%s $n%s %s" % (str(v), str(u), str(topology.edge[v][u]['buffer']))}
        % endif
    % endfor
% endif

% if deploy_stacks:
# Deploy applications and agents
    % for node in topology.nodes_iter():
<%
stack = get_stack(topology, node)
if stack is None:
    continue
stack_name, stack_props = stack
stack_class = stack_props['class']
%>\
${"set %s [new %s]" % (str(stack_name), str(stack_class))}
        % for prop_name, prop_val in stack_props.items():
<% if prop_name == 'class': continue %>\
${"$%s set %s %s" % (str(stack_name), str(prop_name), str(prop_val))}
        % endfor
${"$ns attach-agent $n%s $%s" % (str(node), str(stack_name))}
        % for app_name in get_application_names(topology, node):
<%
app_properties = get_application_properties(topology, node, app_name)
app_class = app_properties['class']
%>\
${"set %s [new %s]" % (str(app_name), str(app_class))}
            % for prop_name, prop_val in app_properties.items():
<% if prop_name == 'class': continue %>\
${"$%s set %s %s" % (str(app_name), str(prop_name), str(prop_val))}
            % endfor
${"$%s attach-agent $%s" % (str(app_name), str(stack_name))}
        % endfor
    % endfor
% endif
"""


def validate_ns2_stacks(topology):
    """
    Validate whether the stacks and applications of a topology are valid for
    ns-2 deployment
    
    Parameters
    ----------
    topology : Topology
        The topology object to validate
        
    Returns
    -------
    valid : bool
        *True* if stacks are valid ns-2 stacks, *False* otherwise
    """
    for node in topology.nodes_iter():
        applications = get_application_names(topology, node)
        for name in applications:
            if not 'class' in get_application_properties(topology, node, name):
                # Each application must have a class attribute to work
                return False
        stack = get_stack(topology, node)
        if stack is None:
            # Each node must have a stack if it has an application
            if len(applications) > 0: return False 
        else:
            # If there is a stack, it must have a class attribute
            if 'class' not in stack[1]: return False
    return True
            

def to_ns2(topology, path, stacks=True):
    """Convert topology object into an ns-2 Tcl script that deploys that
    topology into ns-2.
    
    Parameters
    ----------
    topology : Topology
        The topology object to convert
    path : str
        The path to the output Tcl file
    stacks : bool, optional
        If True, read the stacks on nodes and write them into the output file.
        For this to work, stacks must be formatted in a way understandable by
        ns-2. For example, stack and applications must have a 'class' attribute
        whose value is the name of the ns-2 class implementing it.
        
    Notes
    -----
    In order for the function to parse stacks correctly, the input topology
    must satisfy the following requirements:
     * each stack and each application must have a `class` attribute whose
       value is the ns-2 class implementing such stack or application, such as
       `Agent/TCP` or `Application/FTP`.
     * All names and values of stack and application properties must be valid
       properties recognized by the ns-2 application or protocol stack.
    """
    try:
        from mako.template import Template
    except ImportError:
        raise ImportError('Cannot import mako.template module. '
                          'Make sure mako is installed on this machine.')
    set_buffers = True
    set_delays = True
    # if all links are annotated with weights, then set weights
    set_weights = all('weight' in topology.edge[u][v]
                      for u, v in topology.edges_iter())
    
    if not 'capacity_unit' in topology.graph:
        raise ValueError('The given topology does not have capacity data.')
    if not topology.graph['capacity_unit'] in capacity_units:
        raise ValueError('The given topology does not have a valid capacity unit')
    if not 'buffer_unit' in topology.graph:
        warn('Missing buffer size unit attribute in the topology. '\
             'Output file will be generated without buffer assignments.')
        set_buffers = False
    elif not topology.graph['buffer_unit'] == 'packets':
        warn('The buffer size unit of the topology is %s. The only supported '
             'unit is packets. Output file will be generated without buffer '
             'assignments' % topology.graph['buffer_unit'])
        set_buffers = False
    if not 'delay_unit' in topology.graph or not topology.graph['delay_unit'] in time_units:
        warn('Missing or invalid delay unit attribute in the topology. The '
             'output file will be generated with all link delays set to 0.')
        set_delays = False
    if stacks:
        if not validate_ns2_stacks(topology):
            warn('Some application stacks cannot be parsed correctly. The '
                 'output file will be generated without stack assignments.')
            stacks = False
        if not any('stack' in topology.node[v] for v in topology.nodes_iter()):
            stacks = False
    template = Template(__TEMPLATE)
    variables = {
        'topology':        topology,
        'deploy_stacks':   stacks,
        'set_delays':      set_delays,
        'set_buffers':     set_buffers,
        'set_weights':     set_weights
                }
    with open(path, "w") as out:
        out.write(template.render(**variables))
