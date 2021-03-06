#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import sys, queue, pty, subprocess, select, os
from TouchStyle import *
import configparser

# local files to be ignore when searching for python files
IGNORE = [ "htmlhelper.py", "index.py", os.path.basename(__file__) ]

# a fixed size text widget
class ConsoleWidget(QWidget):
    class Content(object):
        def __init__(self):
            self.w = 0
            self.h = 0
            self.lines = []
            self.cursor = [ 0, 0 ]

            # start with a dummy 80x25 buffer so no
            # input gets lost
            self.resize(80, 25)
            
        def resize(self, w, h):
            # expand existing lines if requied
            if self.w < w:
                for li in range(len(self.lines)):
                    self.lines[li] = self.lines[li] + [' ']*(w-self.w)

            # truncate existing lines if required
            if self.w > w:
                for li in range(len(self.lines)):
                    self.lines[li] = self.lines[li][:w]
                    
            # append empty lines if requied
            if self.h < h:
                for l in range(h - self.h):
                    self.lines.append( [' ']*w)

            # remove lines on top if required
            # TODO: make this depending on cursor position!
            #       first remove lines below the cursor
            if self.h > h:
                remove = self.h - h
                hbelow = self.h - self.cursor[1] - 1

                # can the whole request be satisfied by lines below cursor?
                if remove <= hbelow:
                    # yes, just shrink
                    self.lines = self.lines[:h]
                else:
                    # no, remove as many as possible below, rest above
                    if hbelow: self.lines = self.lines[:-hbelow]
                    self.lines = self.lines[-h:]

                    # move cursor up by the number of lines that have
                    # been removed above it
                    self.cursor[1] = self.cursor[1] - remove
            
            self.w = w
            self.h = h

        def scrollUp(self):
            self.lines = self.lines[1:]
            self.lines.append( [' ']*self.w)
            
        def cursor_right(self):
            self.cursor[0] = self.cursor[0] + 1
            if self.cursor[0] >= self.w:
                self.cursor[0] = 0
                self.cursor_down()
        
        def cursor_down(self):
            self.cursor[1] = self.cursor[1] + 1
            if(self.cursor[1] >= self.h):
                self.scrollUp()
                self.cursor[1] = self.h - 1
        
        def cursor_return(self):
            self.cursor[0] = 0

        def write(self, c):
            # cursor position may already be out of bound if font size
            # has been changed
            if self.cursor[0] < self.w and self.cursor[1] < self.h:
                self.lines[self.cursor[1]][self.cursor[0]] = c;
                    
            self.cursor_right()
            
    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        qsp = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.setSizePolicy(qsp)
        self.content = self.Content()
        self.fontSize = None
        self.bgColor = None
        
        self.readConfig()
        
    def setFont(self, size):
        if size != self.fontSize:
            self.fontSize = size
        
            self.font = QFont("Monospace");
            self.font.setStyleHint(QFont.TypeWriter);
            self.font.setPointSize(self.fontSize)

            metrics = QFontMetrics(self.font)
            self.cw = metrics.width("M")
            self.ch = metrics.height()

            self.repaint()

    def readConfig(self):
        # try to load config from file
        try:
            path = os.path.dirname(os.path.realpath(__file__))
            config = configparser.ConfigParser()
            config.read(os.path.join(path, "console.ini"))
            self.setFont(int(config.get('font','size')))
            bgcolor = config.get('font','bgcolor')
            if bgcolor == "none":
                self.bgColor = None
            else:
                self.bgColor = QColor(bgcolor)
            
        except Exception:
            # if anything goes wrong setup defaults
            self.setFont(10)

    def writeConfig(self):
        # save the address of the device permanently
        path = os.path.dirname(os.path.realpath(__file__))
        cfgfile = open(os.path.join(path, "console.ini"),'w')
        config = configparser.ConfigParser()
        config.add_section('font')
        config.set('font','size', str(self.fontSize))
        if self.bgColor:
            config.set('font','bgcolor', self.bgColor.name())
        else:
            config.set('font','bgcolor', "none")
                       
        config.write(cfgfile)
        cfgfile.close()
            
    def paintEvent(self, event):
        self.w = int(self.width()/self.cw)
        self.h = int(self.height()/self.ch)
        
        if ((self.content.w != self.w) or
            (self.content.h != self.h)):
            # widget size has changed, reset buffer
            self.content.resize(self.w, self.h)
            
        painter = QPainter()
        painter.begin(self)

        # optional set background
        if self.bgColor != None:
            painter.fillRect(event.rect(), self.bgColor)
             
        painter.setFont(self.font)

        for y in range(self.content.h):
            for x in range(self.content.w):
                if self.content.lines[y][x] != ' ':
                    box = QRect(x*self.cw, y*self.ch, self.cw, self.ch)
                    painter.drawText(box, Qt.AlignLeft, self.content.lines[y][x]);

        # draw cursor
        box = QRect(self.content.cursor[0]*self.cw,
                    self.content.cursor[1]*self.ch, self.cw-1, self.ch-1)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("white"))
        painter.drawRect(box);
                
        painter.end()

    def setBlackBg(self, on):
        if on: self.bgColor = QColor("black")
        else:  self.bgColor = None
        self.repaint()
        
    def resizeFont(self, step):
        if self.fontSize + step:
            self.setFont(self.fontSize + step)
        
    def write(self, text):
        # process all characters
        for c in text:
            if c == '\n':
                self.content.cursor_down()
            elif c == '\r':
                self.content.cursor_return()
            else:
                self.content.write(c)
                
        self.repaint();
        
class TextTouchWindow(TouchWindow):
    closed = pyqtSignal()
    
    def __init__(self, title):
        TouchWindow.__init__(self, title)
                
    def close(self):
        self.closed.emit()
        TouchWindow.close(self)
 
class FtcGuiApplication(TouchApplication):
    def __init__(self, args):
        TouchApplication.__init__(self, args)

        path = os.path.dirname(os.path.realpath(__file__))

        # change into current directory before running
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
 
        # Search for python snippet
        program = None
        files = [f for f in os.listdir(path) if os.path.isfile(f)]
        for f in files:
            # file must not be this script itself
            if not f in IGNORE:
                if f.endswith(".py"):
                    program = f
                    break
        
        self.w = TextTouchWindow(program)
        self.w.closed.connect(self.on_close)
        
        self.console = ConsoleWidget(self.w)
        self.w.setCentralWidget(self.console)

        self.menu=self.w.addMenu()
        self.menu.setStyleSheet("font-size: 24px;")
        m_inc = self.menu.addAction("Bigger font")
        m_inc.triggered.connect(self.on_menu_inc)
        m_dec = self.menu.addAction("Smaller font")
        m_dec.triggered.connect(self.on_menu_dec)
        m_black = self.menu.addAction("Black bg")
        m_black.setCheckable(True)
        m_black.setChecked(self.console.bgColor != None)
        m_black.triggered.connect(self.on_menu_black)

        if program:
            # run subprocess
            self.log_master_fd, self.log_slave_fd = pty.openpty()
            self.app_process = subprocess.Popen([ "python3", program ], stdout=self.log_slave_fd, stderr=self.log_slave_fd)

            # start a timer to monitor the ptys
            self.log_timer = QTimer()
            self.log_timer.timeout.connect(self.on_log_timer)
            self.log_timer.start(10)
        else:
            self.console.write("No python script found!")
        
        self.w.show() 
        self.exec_()

    def on_menu_black(self):
        self.console.setBlackBg(self.sender().isChecked())
    
    def on_menu_inc(self):
        self.console.resizeFont(1)
        
    def on_menu_dec(self):
        self.console.resizeFont(-1)
        
    def app_is_running(self):
        if self.app_process == None:
            return False

        return self.app_process.poll() == None
    
    def on_close(self):
        self.console.writeConfig()
            
        if self.app_is_running():
            self.app_process.terminate()
            self.app_process.wait()
        
    def on_log_timer(self):
        # first read whatever the process may have written
        if select.select([self.log_master_fd], [], [], 0)[0]:
            output = os.read(self.log_master_fd, 100)
            if output: 
                self.console.write(str(output, "utf-8"))
        else:
            # check if process is still alive
            if not self.app_is_running():
                if self.app_process.returncode:
                    self.console.write("Application ended with return value " + str(self.app_process.returncode) + "\n")

                # close any open ptys
                os.close(self.log_master_fd)
                os.close(self.log_slave_fd)

                # remove timer
                self.log_timer = None
                
if __name__ == "__main__":
    FtcGuiApplication(sys.argv)
