#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
| Copyright (C) 2017 Johannes Schlatow, Kai-Björn Gemlau, Mischa Möstl
| TU Braunschweig, Germany
| All rights reserved.

:Authors:
         - Johannes Schlatow
         - Kai-Björn Gemlau

Description
-----------

This script parses and analyses the WATERS Challenge Model (given as an Almathea Model).
"""

from waters import AmaltheaParser as atp
from waters import model as waters_model
from waters import path_analysis
from pycpa import graph
from pycpa import analysis
from pycpa import options

import csv

options.parser.add_argument('--model', type=str, required=True,
        help="Almathea model.")
options.parser.add_argument('--print_results', action='store_true',
        help="Print results to terminal.")
options.parser.add_argument('--let_mode', action='store_true',
        help="Use LET communication.")
options.parser.add_argument('--scale', type=float, default=0.7,
        help="Scales execution times (?) in the given model (to render the system schedulable).")
options.parser.add_argument('--delimiter', type=str, default='\t',
        help="CSV delimiter.")
options.parser.add_argument('--wcrt_output', type=str, default=None,
        help="Writes WCRT results as CSV to given file.")
options.parser.add_argument('--mem_output', type=str, default=None,
        help="Writes memory overhead results as CSV to given file.")
options.parser.add_argument('--lat_output', type=str, default=None,
        help="Writes latency results as CSV to given file.")
options.parser.add_argument('--let_task_wcet', type=int, default=50,
        help="Constant execution time for LET Tasks")

def print_wcrt_results(s, task_results=None):
    if options.get_opt('print_results'):
        print("Result:")
        print("Task;Resource;Prio;WCET;BCET;PERIOD;WCRT;readWCET;execWCET;writeWCET;readBCET;execBCET;writeBCET;")
        for r in sorted(s.resources, key=str):
            if r.name != "M1":
                for t in sorted(r.tasks, key=str):
                    if not isinstance(t, waters_model.LETTask):
                        tr = task_results[t]
                        period = t.in_event_model.P
                        print("%s;%s;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d;%d" % (t.name, t.resource.name, t.scheduling_parameter, t.wcet, t.bcet, period, tr.wcrt, tr.readWCET, tr.execWCET, tr.writeWCET, tr.readBCET, tr.execBCET, tr.writeBCET))
                    #period = t.in_event_model.base_event_model.P
        for r in sorted(s.resources, key=str):
            if r.name != "M1":
                print("Load on %s: %s" % (r.name, r.load()))

def write_wcrt_results(system, task_results):
    if options.get_opt('wcrt_output') is not None:
        with open(options.get_opt('wcrt_output'), 'w+') as csvfile:
            writer = csv.writer(csvfile, delimiter=options.get_opt('delimiter'))
            writer.writerow(['Task', 'Resource', 'Prio', 'WCET', 'BCET', 'PERIOD', 
                             'WCRT', 'readWCET', 'execWCET', 'writeWCET', 'readBCET', 'execBCET', 'writeBCET'])


            for r in sorted(system.resources, key=str):
                if not isinstance(r, waters_model.MemoryResource):
                    for t in sorted(r.tasks, key=str):
                        tr = task_results[t]
                        t.update_execution_time(task_results)                            
                        if isinstance(t.in_event_model, waters_model.CorrelatedAccessEventModel):
                            period = t.in_event_model.base_event_model.P
                            readWCET  = 0
                            writeWCET = 0
                            execWCET  = 0
                            readBCET  = 0
                            writeBCET = 0
                            execBCET  = 0
                        else:
                            period    = t.in_event_model.P
                            readWCET  = tr.readWCET
                            writeWCET = tr.writeWCET
                            execWCET  = tr.execWCET
                            readBCET  = tr.readBCET
                            writeBCET = tr.writeBCET
                            execBCET  = tr.execBCET

                        writer.writerow([t.name, t.resource.name, t.scheduling_parameter, t.wcet, t.bcet, period,
                            tr.wcrt, readWCET, execWCET, writeWCET, readBCET, execBCET, writeBCET])

def calc_and_write_latencies(chains, task_results):
    writer = None
    if options.get_opt('lat_output'):
        csvfile = open(options.get_opt('lat_output'), 'w+')
        writer = csv.writer(csvfile, delimiter=options.get_opt('delimiter'))
        writer.writerow(['Name', 'Data Age', 'Reaction Time'])

    if options.get_opt('print_results'):
        print("Analysing cause-effect chain latencies:")
    
    for chain in chains:
        details_age = dict()
        details_rt = dict()
        age = path_analysis.cause_effect_chain_data_age(chain, task_results, details_age)
        rt  = path_analysis.cause_effect_chain_reaction_time(chain, task_results, details_rt)

        if options.get_opt('print_results'):
            print("%s: data age=%d; reaction time=%d" % (chain.name, age, rt))
            print(" data age details:")
            for (entry, value) in details_age.items():
                print("   %s:\t\t%d" % (entry, value))
            print(" reaction time details:")
            for (entry, value) in details_rt.items():
                print("   %s:\t\t%d" % (entry, value))

        if writer is not None:
            writer.writerow([chain.name, age, rt])

def analyze_model(filename):  
    amt_parser = atp.AmaltheaParser(filename, scale = options.get_opt('scale'), 
                                    letMode = options.get_opt('let_mode'),
                                    letTaskWCET = options.get_opt('let_task_wcet'))
    s = amt_parser.parse_amalthea()
    amt_parser.analyzeMemoryOverhead(
            print_results=options.get_opt('print_results'),
            delimiter=options.get_opt('delimiter'),
            outfile=options.get_opt('mem_output'))
    amt_parser.analyzeTaskInteractions()
    amt_parser.analyzeCoreInteractions()
    
    try:
        # plot the system graph to visualize the architecture
        g = graph.graph_system(s, 'waters.pdf')
    except Exception:
        # gracefully pass for machines without matplotlib
        pass
    
    ######################################
    # Perform the response time analysis #
    ######################################
    # We perform two runs of the analysis:
    # The first run is for getting the response times of the memory task which are
    # then used to update the execution times of the runnable tasks.
    # The second run then results in the correct response times of the runnable tasks.
    # As the WCRTs of the memory tasks are independent from any event models, they do not
    # change in the second run.
    ######################################

    print("Performing analysis")
    task_results = analysis.analyze_system(s, progress_hook=None)
    print("Update Execution Times")
    for r in sorted(s.resources, key=str):
        for t in sorted(r.tasks, key=str):
            if isinstance(t, waters_model.RunnableTask):
                t.update_execution_time(task_results = task_results)
            
    print("Second analysis run")
    task_results = analysis.analyze_system(s, progress_hook=None)

    print_wcrt_results(s, task_results)

    write_wcrt_results(s, task_results)
    
    print("....finished")

    calc_and_write_latencies(amt_parser.eventChains, task_results)

def hook(analysis_state):
    print (len(analysis_state.dirtyTasks))

    
if __name__ == "__main__":
    # initialize pyCPA's default command line arguments
    options.init_pycpa()

    # parse and analyze input model
    analyze_model(options.get_opt('model'))
