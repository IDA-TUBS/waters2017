# -*- coding: utf-8 -*-
"""
| Copyright (C) 2017 Johannes Schlatow, Kai-Björn Gemlau, Mischa Möstl
| TU Braunschweig, Germany
| All rights reserved.

:Authors:
         - Mischa Möstl
         - Kai-Björn Gemlau
"""

from __future__ import print_function

import xml.etree.ElementTree as ET
import copy
import csv

from pycpa import model
from waters import model as waters_model
from pycpa import analysis
from waters import schedulers
from pycpa import path_analysis
from pycpa import graph
from pycpa import options
from pycpa import util
from math import ceil

xsi='{http://www.w3.org/2001/XMLSchema-instance}'

class AmaltheaParser(object):
    def __init__(self, xml_file, letMode = False, scale = 1.0, letTaskWCET = 100):
        self.xml_file = xml_file
        # generate an new system
        self.cpa_sys = model.System()
        self.cpa_base = util.ns
        
        self.letMode = letMode
        self.scale = scale
        self.letTaskWCET = letTaskWCET

        root = ET.parse(self.xml_file).getroot()
        self.mappingModel= root.find('mappingModel')
        self.swm = root.find('swModel')
        self.hwModel = root.find('hwModel')
        self.stim = root.find('stimuliModel')
        self.constModle = root.find('constraintsModel')

        self.time_per_instruction = self.set_time_per_instruction() 
        self.cpa_labels= dict()
        self.cores = dict()
        self.cpa_tasks = dict()
        self.runnables = dict()
        
        self.eventChains = list()
        
        self.memoryResource = None
        
    
    def parse_amalthea(self):
        
        self.add_resources()
        self.add_labels()
        self.add_tasks()
        self.add_runnables()
        self.bind_runnables_to_tasks()
        self.bind_labels_to_runables_and_tasks()
        self.bind_tasks_to_cores()
        self.create_memory_tasks()
        self.parse_effect_chains()
        
        if self.letMode:            
            self.create_LET_tasks()

        
        return copy.copy(self.cpa_sys)
    
    def parse_effect_chains(self):
        for effChain in self.constModle.iter('eventChains'):
            name = effChain.get('name')
            stimulus = self.clean_xml_string(effChain.get('stimulus'))[len('RunnableStart_'):]
            e = waters_model.EffectChain(name)

            e.add_element(self.runnables[stimulus])
            for segment in effChain.iter('segments'):
                response = self.clean_xml_string(segment.find('eventChain').get('response'))[len('RunnableStart_'):]
                #labelName = self.clean_xml_string(segment.find('eventChain').get('name'))[len('WR_'):]
                e.add_element(self.runnables[response])
            self.eventChains.append(e)

            e.print_chain()
        
    
    def analyzeMemoryOverhead(self, print_results=True, outfile=None, delimiter='\t'):
        if print_results:
            print("[Task];[Resource];write;read;GRAM")

        writer = None
        if outfile is not None:
            csvfile = open(outfile, 'w+')
            fieldnames = ['Task', 'Resource', 'Priority', 'write', 'read', 'GRAM']
            writer = csv.writer(csvfile, delimiter=delimiter)
            writer.writerow(fieldnames)

        for task_name, task in self.cpa_tasks.items():
            gramWords = 0
            sharedWords = 0
            privateWords = 0
            for label in task.write_labels:
                sharedWords += label.size
            for label in task.read_labels:
                if label.readOnly == True:
                    gramWords += label.size
                else:
                    privateWords += label.size

            if print_results:
                print("%s;%s;%d;%d;%d;%d" % (task_name, task.resource, task.scheduling_parameter, sharedWords, privateWords, gramWords))

            if writer:
                writer.writerow([task_name, task.resource, task.scheduling_parameter, sharedWords, privateWords, gramWords])
        
    def analyzeTaskInteractions(self, outfile="task_interactions.dot"):
        x = len(self.cpa_tasks)+1
        DataStreams = dict()
        DataStreams["M1"] = dict()
        for task_name, task in self.cpa_tasks.items():
            DataStreams[task_name] = dict()
            for t_name, t in self.cpa_tasks.items():
                DataStreams[task_name][t_name] = 0
            DataStreams[task_name]["M1"] = 0
            DataStreams["M1"][task_name] = 0
        for rd_name, rd_task in self.cpa_tasks.items():
            for rd_label in rd_task.read_labels:
                if rd_label.readOnly == True:
                    DataStreams["M1"][rd_name] += rd_label.size
                else:
                    wr_name = rd_label.writeTask.name
                    DataStreams[wr_name][rd_name] += rd_label.size
        
        with open(outfile, 'w+') as out:
            print("digraph {", file=out)
            for wr_stream_name, wr_stream in DataStreams.items():
                for rd_stream_name, rd_stream in wr_stream.items():
                    if rd_stream > 0:
                        thickness = int(ceil((float(rd_stream) / 1000.0) * 5.0))
                        print ("%s -> %s [label=\"%d\",penwidth=\"%d\"];" % (wr_stream_name, rd_stream_name, rd_stream,
                            thickness), file=out)
            print("}", file=out)
        
        
    def analyzeCoreInteractions(self, outfile="core_interactions.dot"):
        DataStreams = dict()
        DataStreams["M1"] = dict()
        for core_name, core in self.cores.items():
            DataStreams[core.name] = dict()
            for c_name, c in self.cores.items():
                DataStreams[core.name][c.name] = 0
            DataStreams[core.name]["M1"] = 0
            DataStreams["M1"][core.name] = 0
            
        for rd_name, rd_task in self.cpa_tasks.items():
            for rd_label in rd_task.read_labels:
                if rd_label.readOnly == True:
                    DataStreams["M1"][rd_task.resource.name] += rd_label.size
                else:
                    wr_task = rd_label.writeTask
                    DataStreams[wr_task.resource.name][rd_task.resource.name] += rd_label.size
        
        with open(outfile, 'w+') as out:
            print("digraph {", file=out)
            for wr_stream_name, wr_stream in DataStreams.items():
                for rd_stream_name, rd_stream in wr_stream.items():
                    if rd_stream > 0:
                        thickness = int(ceil((float(rd_stream) / 2500.0) * 5.0))
                        print ("%s -> %s [label=\"%d\",penwidth=\"%d\"];" % (wr_stream_name, rd_stream_name, rd_stream,
                            thickness), file=out)
            print("}", file=out)    

    def set_time_per_instruction(self):
        assert ( int(self.hwModel.find('coreTypes').get('instructionsPerCycle')) == 1 )
        #Supports only models with one microcontroller element!
        pll_freq = int(float(self.hwModel.find('system/ecus/microcontrollers/quartzes/frequency').get('value')))
        #Assumption: pll_freq is the CPU clock, i.e. prescaler clockRation=1 for each core)
        self.time_per_instruction = util.cycles_to_time(value=1,freq=pll_freq, base_time=self.cpa_base)
        return self.time_per_instruction
    
    def add_resources(self):
        print("Add memory Resource M1")
        memoryScheduler = schedulers.FIFOSchedulerFair(num_cores=4)
        self.memoryResource = waters_model.MemoryResource("M1", read_access_times=(8,8), write_access_times=(8,8), scheduler=memoryScheduler)
        self.cpa_sys.bind_resource(self.memoryResource) 
        
        for core_alloc in self.mappingModel.iter('coreAllocation'):
            r_name = self.clean_xml_string(core_alloc.get('core'))
            sched_name = core_alloc.get('scheduler')
            print("Add Core %s with scheduler-name %s" %(r_name, sched_name))
            if self.letMode:
                #TODO: Fix me
                core = model.Resource(r_name, schedulers.SPPSchedulerWithCritSection())
            else:
                core = model.Resource(r_name, schedulers.SPPSchedulerWithCritSection())
            self.cores[sched_name] = core
            self.cpa_sys.bind_resource(core)    
            
    def add_labels(self):
        for label in self.swm.iter('labels'):
            size = int(ceil(float(label.find('size').get('value'))/32.0))
            name = label.get('name')
            label = waters_model.Label(name, size);
            label.bind_resource(self.memoryResource)
            self.cpa_labels[name] = label
        print("Added %d labels" % (len(self.cpa_labels)))

    def add_tasks(self):
        for t in self.swm.iter('tasks'):
            task_name = t.get('name')
            self.cpa_tasks[task_name] = waters_model.RunnableTask(name = task_name , letMode = self.letMode, scheduling_parameter = int(t.get('priority')))
            self.cpa_tasks[task_name].in_event_model = self.construct_event_model(t)
            #print("Task %s EventModel: %s" % (task_name,self.cpa_tasks[task_name].in_event_model))
        print("Added %d tasks" % (len(self.cpa_tasks)))

    def add_runnables(self):
        for run in self.swm.iter('runnables'):
            name = run.get('name')
            bcet = int(float(run.find('runnableItems/default/deviation/lowerBound').get('value')) * float(self.time_per_instruction) * self.scale)
            wcet = int(float(run.find('runnableItems/default/deviation/upperBound').get('value')) * float(self.time_per_instruction) * self.scale)
            self.runnables[name] = waters_model.Runnable(name, bcet=bcet, wcet=wcet)
        print("Added %d runnables" % (len(self.runnables)))
        
    def bind_labels_to_runables_and_tasks(self):
        for runnable_node in self.swm.iter('runnables'):
            runnable = self.runnables[runnable_node.get('name')]
            cpa_task = runnable.parent_task
            for rItems in runnable_node.iter('runnableItems'):
                attrib = rItems.attrib
                if attrib[xsi+'type'] == "am:LabelAccess":
                    cpa_label = self.cpa_labels[self.clean_xml_string( attrib['data'] )]
                    if attrib['access'] == "read":
                        cpa_task.bind_read_label(cpa_label)
                    elif attrib['access'] == "write":
                        cpa_task.bind_write_label(cpa_label)
                        cpa_label.readOnly = False
                        cpa_label.writeTask = cpa_task
                    else:
                        raise ValueError
        
    def bind_runnables_to_tasks(self):
        for t in self.swm.iter('tasks'):
            task = self.cpa_tasks[t.get('name')]
            for call in t.find('callGraph').find('graphEntries').iter('calls'):
                task.bind_runnable(self.runnables[self.clean_xml_string(call.get('runnable'))])

    def bind_tasks_to_cores(self):
        #add the tasks for the resource
        for task_alloc in self.mappingModel.iter('taskAllocation'): 
            r = self.cores[task_alloc.get('scheduler')]
            task = self.cpa_tasks[self.clean_xml_string(task_alloc.get('task'))]
            r.bind_task(task)
        return None
                    
    def create_memory_tasks(self):
        for core_name, core in self.cores.items():
            for task in core.tasks:
                task.create_and_bind_input_task(self.memoryResource)
                    
                    
    def create_LET_tasks(self):
        for core_name, core in self.cores.items():
            letTasks = list()
            numberOfTasks = len(core.tasks)
            for task in core.tasks:
                offset = task.in_event_model.P - (numberOfTasks * self.letTaskWCET)
                letLabel = waters_model.Label(task.name + ':LET_Label')
                letLabel.bind_resource(self.memoryResource)
                letTasks.append(waters_model.LETTask(parent_task = task, wcet = self.letTaskWCET, offset = offset, letLabel = letLabel))
            for letTask in letTasks:
                core.bind_task(letTask)
        for core_name, core in self.cores.items():
            for task in core.tasks:
                if not isinstance(task, waters_model.LETTask):
                    task.update_let_overhead()
    
    def construct_event_model(self, task_node):
        stimulus_name = self.clean_xml_string(task_node.get('stimuli'))
        for stimulus in self.stim.iter('stimuli'):
            if stimulus.get('name') == stimulus_name:
                return self._em_from_stimulus(stimulus)
        assert False
        return None

    def _em_from_stimulus(self, stimulus=None):
        if stimulus.get(xsi+'type') == "am:Periodic":
            s_param = stimulus.find('recurrence').attrib
            P = util.time_to_time( int(s_param['value']) , base_in=util.str_to_time_base(s_param['unit']), base_out=self.cpa_base)
            return model.PJdEventModel(P=P, J=0)

        elif stimulus.get(xsi+'type') == "am:Sporadic":
            s_param = stimulus.find('stimulusDeviation').find('lowerBound').attrib
            P = util.time_to_time( int(s_param['value']) , base_in=util.str_to_time_base(s_param['unit']), base_out=self.cpa_base)
            return model.PJdEventModel(P=P, J=0)
        else:
            raise ValueError
            
    def clean_xml_string(self, s=None):
        #remove type substring from xml strings
        return s[:s.index('?')]

# vim: tabstop=4 expandtab shiftwidth=4 softtabstop=4
