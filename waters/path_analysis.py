"""
| Copyright (C) 2017 Johannes Schlatow, Kai-Björn Gemlau, Mischa Möstl
| TU Braunschweig, Germany
| All rights reserved.

:Authors:
         - Johannes Schlatow

Description
-----------

This script implements the latency analysis for cause-effect chains.
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import logging
logger = logging.getLogger("pycpa")

from pycpa import model
from pycpa import schedulers
from pycpa import analysis
from . import model as waters_model

def cause_effect_chain_reaction_time(chain, task_results, details=None):
    """ computes the reaction time of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    """
    return _cause_effect_chain_latency(chain, task_results, mode='reaction-time', details=details)

def cause_effect_chain_data_age(chain, task_results, details=None):
    """ computes the data age of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    """
    return _cause_effect_chain_latency(chain, task_results, mode='data-age', details=details)

def _cause_effect_chain_latency(chain, task_results, mode, details):
    """ computes the data age of the given cause effect chain
    :param chain: model.EffectChain
    :param task_results: dict of analysis.TaskResult
    :param mode: either 'data-age' or 'reaction-time'
    """

    sequence = chain.task_sequence()

    if details is None:
        details = dict()

    l_max = 0
    for i in range(len(sequence)):
        # skip first (reader) task
        if i == 0:
            continue

        if i % 2 == 1:
            # add read to write delay
            delay = _read_to_write(sequence[i-1], sequence[i], task_results, details=details)
            logger.info("read to write delay: %d" % delay)
            l_max += delay
        else:
            # add write to read delay
            delay = _write_to_read(sequence[i-1], sequence[i], task_results, backward=(mode == 'data-age'),
                    details=details)
            logger.info("write to read delay: %d" % delay)
            l_max += delay

    return l_max

def _calculate_distance(writer, reader, task_results, details):
    if "ISR" in writer.name:
        result = writer.in_event_model.delta_plus(2) + task_results[writer].wcrt - task_results[writer].bcrt
        details['WR:'+writer.name+':'+reader.name+'-d_plus+J'] = result
        return result
    elif task_results[writer].wcrt >= task_results[reader].wcrt:
        result = writer.in_event_model.delta_plus(2) - task_results[writer].bcrt
        details['WR:'+writer.name+':'+reader.name+'-d_plus-BCRT'] = result
        return result
    else:
        details['WR:'+writer.name+':'+reader.name] = 0
        return 0

def _period(task):
    if isinstance(task, waters_model.LETTask):
        return task.in_event_model.base_event_model.P
    else:
        return task.in_event_model.P

def _calculate_forward_distance(writer, reader, task_results, details):
    """ computes forward distance (for reaction time)
    """
    
    if _period(reader) > _period(writer):
        # undersampling delay
        result = reader.in_event_model.delta_plus(2)
        details['WR:'+writer.name+':'+reader.name+'-d_plus'] = result
        return result

    elif isinstance(writer, waters_model.LETTask):
        # LET delay is already accounted by read-to-write delay
        details['WR:'+writer.name+':'+reader.name] = 0
        return 0

    else:
        return _calculate_distance(writer, reader, task_results, details)

def _calculate_backward_distance(writer, reader, task_results, details):
    """ computes forward distance (for data age)
    """

    if _period(reader) < _period(writer):
        # oversampling delay
        result = writer.in_event_model.delta_plus(2) + task_results[writer].wcrt - task_results[writer].bcrt
        details['WR:'+writer.name+':'+reader.name+'-d_plus+J'] = result
        return result

    elif isinstance(writer, waters_model.LETTask):
        # LET delay is already accounted by read-to-write delay
        details['WR:'+writer.name+':'+reader.name] = 0
        return 0

    else:
        return _calculate_distance(writer, reader, task_results, details)
    
def _write_to_read(writer, reader, task_results, details, backward=False):
    """ computes the write to read distance between two tasks
    """

    # determine whether we have intra-task communication
    intra_task = False
    if isinstance(writer, waters_model.LETTask):
        if reader.LETTask == writer:
            intra_task = True
    elif reader == writer:
        intra_task = True

    # calculate delay
    if intra_task:
        # backward intra-task communication
        if isinstance(writer, waters_model.LETTask):
            # LET communication
            details['WR:'+writer.name+':'+reader.name] = 0
            return 0
        else:
            # implicit communication
            result = reader.in_event_model.delta_plus(2) - task_results[reader].bcrt
            details['WR:'+writer.name+':'+reader.name+'-d_plus-BCRT'] = result
            return result
    else:
        # inter-task communication
        if backward:
            return _calculate_backward_distance(writer, reader, task_results, details)
        else:
            return _calculate_forward_distance(writer, reader, task_results, details)

def _read_to_write(reader, writer, task_results, details):
    """ computes the read to write distance between two tasks
    """
    details_name = 'RW:'+reader.name+':'+writer.name

    if isinstance(writer, waters_model.LETTask):
        # assuming LET = Period
        result = writer.in_event_model.base_event_model.P
        details[details_name+'-LET'] = result
        return result

    else:
        assert(writer == reader)
        result = task_results[reader].wcrt
        details[details_name+'-WCRT'] = result
        return result
            
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
