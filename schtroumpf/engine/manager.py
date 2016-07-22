# peiqi shi 2016.07.20 
from threading import Event
from threading import Thread
from Queue import Queue


class Manager(Thread):

    def __init__(self):
        super(Manager, self).__init__(name="Manager of lastroumpf")
        #self.setDaemon(True)
        self.StopEvent = Event()

    def run(self):
        while True:
            if self.StopEvent.isSet():
                print "%s namely %s is started "% (self.name,self.ident)
                break

    def _stop(self):
        self.StopEvent.set()

    def _print(self):
        print self.StopEvent.isSet()


class Main(object):

    def __init__(self):
        self.thread1 = Manager()
        self.thread2 = Manager()

    def start(self):
        self.thread1.start()
        self.thread2.start()
        self.thread2._stop()
        self.thread1._stop()
        self.thread1._print()

if __name__ == '__main__':
    thread2 = Main()
    thread2.start()
