from waters import AmaltheaParser as atp
from pycpa import analysis

TESTFILE='Test.xml'

# def test_label_size(xml_file=None):
#     swm = ET.parse(xml_file).getroot().find('swModel')
# 
#     for labels in swm.iter('labels'):
#         lname = labels.get('name')
#         lsize = int(labels.find('size').get('value'))
#         assert (labels.find('size').get('unit') == 'bit') , "Value is not bit!"
#         if lsize > 32:
#             print (lname, lsize)

def test_parser():
    amt_parser = atp.AmaltheaParser(TESTFILE)
    s = amt_parser.parse_amalthea()

    for r in s.resources:
        for t in r.tasks:
            print ("Task %s on Resource %s" % (t.name,r.name))
            for runnable in t.runnables:
                print("\t Runnable %s" % (runnable.name))
                for w_label in runnable.write_labels:
                    print("\t\t Writes Label: %s" % (w_label.name))
                for r_label in runnable.read_labels:
                    print (" \t\t Reads Label: %s" % (r_label.name))

def print_task_model():
    
    amt_parser = atp.AmaltheaParser(TESTFILE)
    s = amt_parser.parse_amalthea()
     
    for r in s.resources:
        for t in r.tasks:
            t.wcet = sum(runnable.wcet for runnable in t.runnables)
            t.bcet = sum(runnable.bcet for runnable in t.runnables)
            print ("Task %s on Resource %s \t WCET: %s, BCET: %s EventModel: %s" % \
                    (t.name,r.name,t.wcet,t.bcet, type(t.in_event_model)))


            

    #print("Performing analysis")
    #task_results = analysis.analyze_system(s)

if __name__ == "__main__":
    #test_label_size(TESTFILE)
    #test_parser()
    print_task_model()

