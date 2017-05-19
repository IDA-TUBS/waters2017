"""
| Copyright (C) 2017 Johannes Schlatow, Kai-Björn Gemlau, Mischa Möstl
| TU Braunschweig, Germany
| All rights reserved.

:Authors:
         - Johannes Schlatow
         - Kai-Björn Gemlau
"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals
from __future__ import division

import math
import logging
import copy
import warnings

from pycpa import model

logger = logging.getLogger(__name__)

class MemoryTask(model.Task):

    def __init__(self, name, parent_task, *args, **kwargs):
        model.Task.__init__(self, name, *args, **kwargs)

        self.labels = list()
        self.parent_task = parent_task

    def update_execution_time(self, *args):
        self.wcet = 0
        self.bcet = 0
        for label in self.labels:
            self.wcet += label.read_access_wcet()
            self.bcet += label.read_access_bcet()


    def bind_label(self, label):
        self.labels.append(label)
        return label

    def get_mutex_interferers(self):
        return [self.parent_task]
    
class LETTask (model.Task):

    def __init__(self, parent_task, wcet = 50, offset = 0, letLabel = None, *args, **kwargs):
        model.Task.__init__(self, parent_task.name +':LET_Task', scheduling_parameter = parent_task.scheduling_parameter+100,*args, **kwargs)

        self.in_event_model = CorrelatedAccessEventModel(parent_task.in_event_model, offset)
        self.parentTask = parent_task
        self.wcet = wcet       #choose a constant execution time
        self.bcet = wcet
        self.letLabel = letLabel
        parent_task.LETTask = self        
    
class MemoryResource(model.Resource):
    
    def __init__(self, name, read_access_times, write_access_times, scheduler, **kwargs):

        model.Resource.__init__(self, name, scheduler, **kwargs)

        self.read_access_wcet = read_access_times[0]
        self.read_access_bcet = read_access_times[1]
        self.write_access_wcet= write_access_times[0]
        self.write_access_bcet= write_access_times[1]

class Label(object):

    def __init__(self, name, size=1, writeTask=None):

        self.name = name
        self.size = 1
        self.resource = None
        self.readOnly = True
        self.writeTask = writeTask

    def bind_resource(self, resource):
        self.resource = resource
        return resource

    def read_access_wcet(self):
        assert(self.resource is not None)
        return self.size * self.resource.read_access_wcet

    def read_access_bcet(self):
        assert(self.resource is not None)
        return self.size * self.resource.read_access_bcet

    def write_access_wcet(self):
        assert(self.resource is not None)
        return self.size * self.resource.write_access_wcet

    def write_access_bcet(self):
        assert(self.resource is not None)
        return self.size * self.resource.write_access_bcet

class CorrelatedAccessEventModel(model.EventModel):
    def __init__(self, base_event_model, offset, *args, **kwargs):
        model.EventModel.__init__(self, base_event_model.__description__ + ':corr', *args, **kwargs)

        self.base_event_model = base_event_model
        self.offset = offset

    def deltamin_func(self, n):
        return self.base_event_model.deltamin_func(n)

    def deltaplus_func(self, n):
        return self.base_event_model.deltaplus_func(n)

    def correlated_dmin(self, task):
        assert(isinstance(task.in_event_model, CorrelatedAccessEventModel))

        if self.base_event_model is task.in_event_model.base_event_model:
            return self.offset - task.in_event_model.offset
        else:
            return 0
        
class Runnable(object):
    def __init__(self, name, bcet, wcet):
        self.wcet = wcet
        self.bcet = bcet
        self.name = name
        self.parent_task = None

        self.read_labels = list()
        self.write_labels = list()

    def bind_read_label(self, label):
        self.read_labels.append(label)
        return label

    def bind_write_label(self, label):
        self.write_labels.append(label)
        return label

    def position(self):
        # the name of the runnable determines its position in the task
        return int(self.name[self.name.rfind('_')+1:])


class RunnableTask(model.Task):

    def __init__(self, name, letMode = False, *args, **kwargs):
        model.Task.__init__(self, name, *args, **kwargs)
        
        self.letMode = letMode
        self.runnables = list()
        self.read_labels = list()
        self.write_labels = list()
        self.memory_input_task = None
        self.memory_output_task = None
        self.LETTask = None
        self.LETOverhead = 0

    def reader(self):
        return self

    def writer(self):
        if self.LETTask is not None:
            return self.LETTask

        return self
    
    def bind_runnable(self, runnable):
        runnable.parent_task = self
        self.runnables.append(runnable)
        return runnable
    
    def bind_read_label(self, label):
        self.read_labels.append(label)
        return label
 
    def bind_write_label(self, label):
        self.write_labels.append(label)
        return label
    
    def bind_LET_Task(self, LETTask):
        self.LETTask = LETTask

    def update_let_overhead(self):
        producerTasks = list()
        for label in self.read_labels:
            if label.readOnly == False and label.writeTask not in producerTasks:
                producerTasks.append(label.writeTask)
                self.memory_input_task.bind_label(label.writeTask.LETTask.letLabel)
                self.memory_input_task.update_execution_time()
                self.update_execution_time()
        print ("%s, %d" % (self.name, len(producerTasks)))

    def update_execution_time(self, task_results = None):
        #WCET = sum of all runnables + wcrt of memory task + time for all write-labels
        execWCET = sum(runnable.wcet for runnable in self.runnables)
        if task_results != None:
            readWCET = task_results[self.memory_input_task].wcrt
        else:
            readWCET = self.memory_input_task.wcet
        writeWCET = sum(label.size for label in self.write_labels)
        self.wcet = execWCET + readWCET + writeWCET
        if self.letMode:
            self.wcet += self.LETOverhead
            
        #BCET = sum of all runnables + bcet of memory task + 
        execBCET = sum(runnable.bcet for runnable in self.runnables)
        readBCET = self.memory_input_task.bcet
        writeBCET = sum(label.size for label in self.write_labels)
        self.bcet = execBCET + readBCET + writeBCET
        if self.letMode:
            self.bcet += self.LETOverhead
            
        if task_results != None:
            tr = task_results[self]
            tr.wcet = self.wcet
            tr.bcet = self.bcet
            tr.readWCET = readWCET
            tr.readBCET = readBCET
            tr.writeWCET = writeWCET
            tr.writeBCET = writeBCET
            tr.execWCET = execWCET
            tr.execBCET = execBCET
            if self.letMode:
                tr.letOverhead = self.LETOverhead

    def create_and_bind_input_task(self, resource):
        # find all read labels mapped to given resource and create task from these labels
        task = MemoryTask(self.name + ':readlabels', parent_task=self)
        if self.name == "Task_10ms":
            pass
        self.memory_input_task = task
        task.in_event_model = CorrelatedAccessEventModel(self.in_event_model, 0)
        for l in self.read_labels:
            if l.resource is resource:
                task.bind_label(l)
        if len(task.labels) > 0:
            task.update_execution_time()
            self.update_execution_time()
            resource.bind_task(task)
    
class EffectChain():
    def __init__(self, name):
        # list of runnables in the effect chain
        self.runnables = list()
        self.name = name
        
    def add_element(self, runnable):
        """ Add runnable to the effect chain.

            The assumption is, that the runnable reads the label which is written by the previous runnable and writes
            another label itself.
            A runnable therefore acts as a read and a writer.
        """
        self.runnables.append(runnable)

    def task_sequence(self):
        """ Generates and returns the sequence of reader/writer tasks in the form of [reader_, writer_0, reader_1, writer_1,...].
            
            A task in this sequence therefore acts either as a reader or a writer. Tasks at odd positions in this
            sequence are readers while tasks at even positions are writers.
        """

        sequence = list()

        for i in range(len(self.runnables)):
            r = self.runnables[i]
            task = None

            # check for intra task communication
            if i > 0 and self.runnables[i-1].parent_task == r.parent_task:
                if r.position() < self.runnables[i-1].position():
                    # backward communication -> we must add this task to the sequence
                    task = r.parent_task
                else:
                    task = None
            else:
                task = r.parent_task

            if task is not None:
                # add reading and writing tasks
                sequence.append(task.reader())
                sequence.append(task.writer())

        return sequence
    
    def print_chain(self):
        queue = ""
        for run in self.runnables:
            queue += " -> " + run.name
        print (queue)
        queue = ""
        for t in self.task_sequence():
            queue += " -> " + t.name
        print(queue)

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
