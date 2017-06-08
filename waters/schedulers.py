# -*- coding: utf-8 -*-
"""
| Copyright (C) 2017 Johannes Schlatow, Kai-Björn Gemlau, Mischa Möstl
| TU Braunschweig, Germany
| All rights reserved.

:Authors:
         - Kai-Björn Gemlau
         - Johannes Schlatow

Description
-----------

This script implements the schedulers for the memory resources and processing resources.
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import itertools
import math
import logging

from pycpa import schedulers
from pycpa import analysis
from . import model

amalthea_high_prio_wins = lambda a, b : a >= b

class FIFOSchedulerFair(analysis.Scheduler):
    """ Fair FIFO scheduler for memory accesses.
        This scheduler bases on the assumption that each access is (at most) interfered
        by one access from each of the interfering cores.
    """

    def __init__(self, num_cores):
        analysis.Scheduler.__init__(self)

        self.num_cores        = num_cores

    def b_plus(self, task, q, details=None, task_results=None):
        assert(task.wcet >= 0)

        w = task.wcet * self.num_cores #for the memory tasks, it wcet is multiplied by number of cores

        return w

class SPPSchedulerWithCritSection(analysis.Scheduler):

    def __init__(self, priority_cmp=amalthea_high_prio_wins):
        analysis.Scheduler.__init__(self)

        # # priority ordering
        self.priority_cmp = priority_cmp
        
    def get_largestCriticalSection(self, task, task_results):
        size = 0
        for ti in task.get_resource_interferers():
            if("LET" in ti.name):
                if(ti.wcet >= size):
                    size = ti.wcet      #This is an LET Task
            elif(task_results[ti.memory_input_task].wcrt >= size):
                    size = task_results[ti.memory_input_task].wcrt                
            
        return size
            
    def b_plus(self, task, q, details=None, **kwargs):
        """ This corresponds to Theorem 1 in [Lehoczky1990]_ or Equation 2.3 in [Richter2005]_. """
        assert(task.scheduling_parameter != None)
        assert(task.wcet >= 0)

        w = q * task.wcet

        if task.name == "Task_20ms":
            pass

        while True:
            # logging.debug("w: %d", w)
            # logging.debug("e: %d", q * task.wcet)
            s = self.get_largestCriticalSection(task,kwargs["task_results"])
            # logging.debug(task.name+" interferers "+ str([i.name for i in task.get_resource_interferers()]))
            for ti in task.get_resource_interferers():
                assert(ti.scheduling_parameter != None)
                assert(ti.resource == task.resource)
                
                if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):  # equal priority also interferes (FCFS)
                    if isinstance(ti, model.LETTask):
                        if s + q * task.wcet >= ti.in_event_model.offset:
                            s += ti.wcet * ti.in_event_model.eta_plus(w)
                    else:
                        s += ti.wcet * ti.in_event_model.eta_plus(w)
                        #print ("Task: %s, s: %d, w: %d" % ()
                    # logging.debug("e: %s %d x %d", ti.name, ti.wcet, ti.in_event_model.eta_plus(w))

            w_new = q * task.wcet + s
            # print ("w_new: ", w_new)
            if w == w_new:
                assert(w >= q * task.wcet)
                if details is not None:
                    details['q*WCET'] = str(q) + '*' + str(task.wcet) + '=' + str(q * task.wcet)
                    for ti in task.get_resource_interferers():
                        if self.priority_cmp(ti.scheduling_parameter, task.scheduling_parameter):
                            if isinstance(ti, model.LETTask):
                                if w > ti.in_event_model.offset:
                                    details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w)) + '*'\
                                        + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w))
                            else:
                                details[str(ti) + ':eta*WCET'] = str(ti.in_event_model.eta_plus(w)) + '*'\
                                    + str(ti.wcet) + '=' + str(ti.wcet * ti.in_event_model.eta_plus(w))
                return w

            w = w_new
            
# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
