import math
import os
import sys
import time

import numpy as np
import matplotlib as mpl

if sys.platform == 'darwin':
    mpl.use('macosx')

import matplotlib.pyplot as plt
import matplotlib.widgets as mpl_w
import matplotlib.gridspec as gridspec

import csv
import h5py
from datetime import datetime
import time

global VERSION_NUMBER
VERSION_NUMBER = "0.9.9.15"

class EyeDataPlot:
    def __init__(self, filepath, coder, targetList=[], targetDuration=1.000, timeAfterTarget=0.125, fixationWindowSec = 0.250):
        self.readData(filepath)

        self.interests = ['time', '# count', \
                 'left_gaze_x','left_gaze_y', \
                 'right_gaze_x','right_gaze_y', \
                 'posx', 'posy', \
                 'ROW_INDEX']

        self.coder = coder  # Identifier for person doing coding
        self.targetDuration  = targetDuration  # sec
        self.timeAfterTarget = timeAfterTarget  # sec
        self.moveToNextTarget = False
        self.targetNumber = 0
        self.fixationWindowSec = fixationWindowSec
        self.filepath = filepath

        self.fileName = filepath.split('/')[-1]#; print(self.fileName)
        self.csvFileName = filepath[:-4] + '_' + coder + \
                           datetime.now().strftime('_%Y-%m-%d_%H-%M') + '.csv' # Output filename
        
        self.firstPass = True  # So we can initialize the plots

        if targetList == []:
            self.targetList = list(range(1,50))
            #random.shuffle(self.targetList)
        else:
            self.targetList = list(filter(lambda t:0<=t<=48, targetList)) #removes targets that are not in the range [0,48]

        global readyForClick

        self.XYplotLimits = [-30., 30., -100., 100.]  # Initialize to nonsense values ...
        readyForClick = False

    def readData(self, filepath):
        self.table = []

        ###opening the file and reading in the data###

        if filepath[-4:] == '.dat' or filepath[-4:] == '.txt': #for now, .txt assumed to be tab-delimited
            file = open(filepath)
            lines = file.read().split('\n')
            file.close()
            for line in lines:
                self.table.append( line.split('\t') ) #.dat is assumed to be tab-delimited
            self.table.pop()
        elif filepath[-5:] == '.hdf5':
            file = h5py.File(filepath,'r')

            if '2.3' in h5py.version.version:
                trim = lambda s: s
            else: #'2.5' in h5py.version.version:
                trim = lambda s: s[2:-1] #necessary because 2.5.0 imports strings as b'...' instead of just ...
            
            stimulusData = file.get('/data_collection/condition_variables/EXP_CV_1') #experiment variables
            sHcutoff = (len(stimulusData.attrs.values())-4)//2 + 3
            stimulusHeader = list(map(lambda x: trim(str(x)),stimulusData.attrs.values()))[3:sHcutoff]
            
            trackerData = file.get('/data_collection/events/eyetracker/BinocularEyeSampleEvent') #works even for monocular trackers
            tHcutoff = (len(trackerData.attrs.values())-4)//2 + 3
            trackerHeader = list(map(lambda x: trim(str(x)),trackerData.attrs.values()))[3:tHcutoff]

            trackerHeader[trackerHeader.index('time')] = 'device_time_2'
            trackerHeader[trackerHeader.index('logged_time')] = 'time' #needed to make the rest of the code work

            r = 0
            sDrow = stimulusData[0]
            grabData = 0 #required to drop rows until times match up
            
            self.table.append(stimulusHeader + trackerHeader) #header strings
            for row in list(trackerData): #trackerData is iterable in h5py 2.5.0, but not 2.3.0
                if grabData == 1:
                    if row['logged_time'] > sDrow['TRIAL_END']:
                        r += 1
                        if r >= len(stimulusData): break

                        sDrow = stimulusData[r]
                        if sDrow['BLOCK'] == b'SP': break
                        
                    self.table.append(list(sDrow)+list(row))
                else:
                    if row['logged_time'] > sDrow['TRIAL_START']:
                        grabData = 1
                        self.table.append(list(sDrow)+list(row))

        if '# count' not in self.table[0]:
            self.table[0].append('# count')
            for k in range(len(self.table)-1):
                self.table[k+1].append(k)

    def extractData(self):
        ###preliminary processing###
        self.header = self.table.pop(0) #separate header from data

        self.interests = list(filter(lambda i: self.header.count(i), self.interests)) #filter out interests that aren't in the table
        self.indices = [ self.header.index(i) for i in self.interests ] #column indices of those interests
        
        ###data extraction###
        #"one"-liner magic!
        #data is a dictionary where the interests are keys whose values are lists that contain their respective columns
        #nonan is the same as data, except that any line with a "nan" somewhere was excluded; hence, there are *no nan*s...
        if sys.version_info[0] >= 2:
            data  = dict(zip(self.interests, zip( *[[float(row[k]) for k in self.indices] for row in self.table] ) ))
            nonan = dict(zip(self.interests,
                             zip(
                                 *list(filter(lambda y: len(y)==len(self.indices),
                                              [ list(filter(lambda x: not math.isnan(x),
                                                            [float(row[k]) for k in self.indices] )) for row in self.table] )) ) ))

        self.data = data
        self.nonan = nonan
        self.dataN = len(data['time']) #number of elements in data/nonan
        self.nonanN = len(nonan['time'])

        self.Hz = (self.dataN-1)/(data['time'][-1] - data['time'][0])   # calculate the hertz
        #print('Averge sampling frequency = {:5.2f} Hz'.format(self.Hz)) # check on the speed

        self.mode = 2 if self.table[0][2]=="Binocular" else 1 #used for calculating the expected number of targets

        # Create output datafile, and write header
        self.csvfile = open(self.csvFileName, 'w')
        self.fileWriter = csv.writer(self.csvfile, delimiter=',', lineterminator='\n')
        self.fileWriter.writerow(['filepath: '+self.filepath,
                                  'coder: '+self.coder,
                                  'version: '+VERSION_NUMBER,
                                  'day/time: '+datetime.now().strftime('%Y-%m-%d_%H-%M'),
                                  'number: '+str(self.mode*len(self.targetList)),
                                  'frequency (Hz): {:5.2f}'.format(self.Hz)
                                  ]
                                 )

        headerList = ['Coded by', 'Filename', 'EyeLeftRight', 'Target#', 'targetX', 'targetY', 'Onset (sec)',
                      'Range start (sec)', 'range start delay', 'range start quality', 'Range end (sec)', 'range end delay', 'range end quality', 'range duration', 'range nonan count x', 'range nonan count y',
                      'Window start (sec)', 'window start delay', 'Window end (sec)', 'window end delay', 'window quality', 'window duration', 'window nonan count x', 'window nonan count y']
        
        for span in ['r_','w_']:
            for kind in ['X','XErr','Y','YErr','PythErr']:
                for moment in ['mean','median','mode','stdDev','min','max']:
                    headerList.append(span+moment+kind)
                    
        self.fileWriter.writerow(headerList)

    class figure: #not to be confused with plt.figure

        mpl.rcParams['toolbar'] = 'None'  # Disable toolbar on matplotlib windows

        class Cursor:
            def __init__(self, ax, ax2, timeWindow, showText=False, XYplotLimits=[] ):
                self.ax = ax
                self.ax2 = ax2

                self.ly_aS = ax.axvline(color='g', linewidth=3)
                self.ly_aS_2 = ax2.axvline(color='g', linewidth=3)
                self.ly_aE = ax.axvline(color='r', linewidth=3)
                self.ly_aE_2 = ax2.axvline(color='r', linewidth=3)
                
                self.ly_wS = ax.axvline(color='k')
                self.ly_wS_2 = ax2.axvline(color='k')
                self.ly_wE = ax.axvline(color='k')
                self.ly_wE_2 = ax2.axvline(color='k')
                
                self.lx_thresh = ax.axhline(color='r', linewidth=3)  # the horizontal quality threshold line
                self.timeWindow = timeWindow
                self.mouseTimeVal = 0.0  # Initialize x-value of mouse position
                self.qualityMetric = 1.0  # Initialize y-value of mouse position
                
                self.confirmClick = False
                self.durTooSmall = False
                self.clickTime = time.clock()
                self.clickDelay = 0.250

                self.clicks = 0
                self.acceptableStart = 0.0
                self.aS_quality = 1.0
                self.acceptableEnd = 0.0
                self.aE_quality = 1.0
                self.windowStart = 0.0
                self.windowEnd = 1.0
                self.wSE_quality = 1.0

                self.aS = 0
                self.aE = 0
                self.wS = 0

                self.XYplotLimits = XYplotLimits

                # text location in axes coords
                self.txt = ax.text( 0.17, 0.92, '', transform=ax.transAxes, color='r', size=16)

                lQ_ratio = 0.1
                self.lowQualityThreshold = XYplotLimits[0] + (XYplotLimits[1] - XYplotLimits[0])*lQ_ratio
                self.lx_thresh.set_ydata(self.lowQualityThreshold)

            def mouse_move(self, event):
                if not event.inaxes == self.ax: return  # Only continue if mouse is in one of the axes

                x, y = event.xdata, event.ydata
                self.mouseTimeVal = x

                if y <= self.lowQualityThreshold:
                    if self.confirmClick == False:
                        self.txt.set_text( 'MARK AS LOW-QUALITY DATA')
                    else:
                        self.txt.set_text( 'CLICK BELOW THE RED LINE TO CONFIRM')
                elif self.clicks == 2 and self.aE - self.aS < self.timeWindow:
                    self.txt.set_text( 'DURATION TOO SMALL. CLICK TO CONTINUE.' )
                    self.durTooSmall = True
                else:
                    self.txt.set_text( ' ')

                self.qualityMetric = (y-self.lowQualityThreshold)/(self.XYplotLimits[1] - self.lowQualityThreshold)

                # update the relevant line positions
                if self.clicks == 0:
                    self.ly_aS.set_xdata(x )
                    self.ly_aS_2.set_xdata(x )
                elif self.clicks == 1:
                    self.ly_aE.set_xdata(max([x,self.aS]) )
                    self.ly_aE_2.set_xdata(max([x,self.aS]) )
                elif self.clicks == 2 and not (self.aE - self.aS < self.timeWindow):
                    self.ly_wS.set_xdata( min([max([x,self.aS]), self.aE-self.timeWindow]) )
                    self.ly_wS_2.set_xdata( min([max([x,self.aS]), self.aE-self.timeWindow]) )
                    self.ly_wE.set_xdata( min([max([x,self.aS]), self.aE-self.timeWindow]) + self.timeWindow )
                    self.ly_wE_2.set_xdata( min([max([x,self.aS]), self.aE-self.timeWindow]) + self.timeWindow )

                global readyForClick
                readyForClick = True

                plt.draw()

        def __init__(self, idnum, XYplotLimits):  ## init for Class figure

            self.fig = plt.figure(idnum, figsize=(16, 6), dpi=80) #the figure
            self.subs = {} #subplots
            self.axes = {} #axes for positioning widgets
            self.widgets = {} #sliders, buttons, etc.
            self.lines = {} #graphed lines

            self.XYplotLimits = XYplotLimits

            #  subplots
            gs = gridspec.GridSpec(12, 2)  # 12 rows, 2 columns
            self.subs['time_xy_sub'] = self.fig.add_subplot(gs[0:8,0]) #top left, has raw data, filtered data, and target positions
            self.subs['error_sub'] = self.fig.add_subplot(gs[9:12,0], sharex=self.subs['time_xy_sub']) #bottom left, has Pythagorean error
            self.subs['velocity_sub'] = self.subs['error_sub'].twinx() #and velocity
            self.subs['x_vs_y_sub'] = self.fig.add_subplot(gs[0:12,1]) #right, has eye trace and target grid
            gs.update(left=0.05, right=0.98, top=0.95, bottom=0.05, wspace=0.10, hspace=0.05)
            
        ###functions for plotting stuff###

        def calcXYGrid(self, data, attrs): #identifies distinct target points

            gridXpt = [data['posx'][0]] # start with the first target point
            gridYpt = [data['posy'][0]]
            dataN = len(data['time'])
            
            for k in range(dataN):
                if data['posx'][k] != gridXpt[-1] or data['posy'][k] != gridYpt[-1]: #new target point location that's different from the most recent
                    gridXpt.append(data['posx'][k]) #add new target point location to list
                    gridYpt.append(data['posy'][k])

            self.XYplotLimits = [min(gridXpt)*1.5, max(gridXpt)*1.5, min(gridYpt)*1.5, max(gridYpt)*1.5]

            return (gridXpt,gridYpt) #return target x and y together

        def graphXYGrid(self, data, attrs, sub, style='x'): #2D graph for target grid
            (calGridX, calGridY) = self.calcXYGrid(data, attrs) #get target grid xs and ys and graph them

            self.plotXvsY(data, attrs, sub, style)

            sub.set_xlim([self.XYplotLimits[0] - 5, self.XYplotLimits[1] + 5]) #don't autozoom out if there are data points far away from target grid
            sub.set_ylim([self.XYplotLimits[2] - 3, self.XYplotLimits[3] + 3])

        def plotDataVsTime(self, data, attrs, sub, style='-'): #graph data lists that correspond to the ones in attrs
            for attr in attrs[1:]: #for each attribute, plot that data against time
                line, = sub.plot(data[attrs[0]], data[attr], style, label=attr)
                self.lines[attr] = line

            if attr == 'velocity':
                sub.legend(bbox_to_anchor=(0., 0., 1., 1.03), loc='upper right', prop={'size':10}) #creates legend and makes text smaller so the box doesn't take up too much space
            elif attr == 'pyth_err':
                sub.legend(bbox_to_anchor=(0., 0., 1., 1.04), loc='upper left', prop={'size':10}) #creates legend and makes text smaller so the box doesn't take up too much space
            else:  # X & Y, raw & filtered, posx & posy
                sub.legend(bbox_to_anchor=(0., 0., 1., 1.08), loc='upper left', ncol=1, prop={'size':8}) #creates legend and makes text smaller so the box doesn't take up too much space

            #sub.set_ylim([self.XYplotLimits[2] - 3, self.XYplotLimits[3] + 3])

        def plotXvsY(self, data, attrs, sub, style='-'): #2D graph plotting attrs[0] versus attrs[1]
            if attrs[0].count('_') > 0:
                side = attrs[0][: attrs[0].index('_') ] #will be 'left' or 'right'
            else:
                side = attrs[0] #generally, 'posx'

            line, = sub.plot(data[attrs[0]], data[attrs[1]], style, label=side) #plots the data
            self.lines[side] = line

            sub.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=7, ncol=2, prop={'size':10}) #creates the legend
            return line #useful for getting the eye trace

        def addCursor(self, axName, ax2Name, timeWindow, showText=False, ): #for the vertical bars on the time vs data plot

            ax = self.subs[axName]
            ax2 = self.subs[ax2Name]

            cursor = self.Cursor(ax, ax2, timeWindow, showText=False, XYplotLimits = self.XYplotLimits)
            self.widgets[axName+'_cursor'] = cursor

            return self.widgets[axName+"_cursor"]

        def getXYplotLimits(self):
            return self.XYplotLimits

    def makeFigs(self): #automatically generates figure(s) for left and/or right eye(s)
        self.extractData() #extract relevant data from all data

        ###plot stuff###
        def createFigure(attrs, iden):

            global globalVmax

            fig = self.figure(iden, XYplotLimits=self.XYplotLimits) #create a pyplot figure

            x = attrs[0] #'left_gaze_x' or 'right_gaze_x'
            y = attrs[1] #'left_gaze_y' or 'right_gaze_y'

            data = self.data
            nonan = self.nonan

            #2D plot
            xy_sub = fig.subs['x_vs_y_sub']
            
            fig.lines['currTarget'], = xy_sub.plot([0,0], [0,0], 'rx', markersize=12.0, markeredgewidth=2.0)
            fig.lines['trace'] = fig.plotXvsY(nonan, [x,y], xy_sub, style='o-') # 2D eye trace
            fig.graphXYGrid(data, ['posx','posy'], xy_sub) #target grid

            self.XYplotLimits = fig.getXYplotLimits()

            #data vs time
            self.t_xy_sub = fig.subs['time_xy_sub']

            fig.plotDataVsTime(data, ['# count',x,y], fig.subs['time_xy_sub'], style='.-') #raw data
            fig.plotDataVsTime(data, ['# count','posx','posy'], fig.subs['time_xy_sub'], style='--') #target position

            self.t_xy_sub.set_ylim(min(self.XYplotLimits[0], self.XYplotLimits[2]),
                                   max(self.XYplotLimits[1], self.XYplotLimits[3]))

            #error/velocity sub plots
            P = calculatePythagoreanError(x,y, data, nonan)
            nonan['pyth_err'] = P #again, because nans are excluded
            err_sub = fig.subs['error_sub'] #get only the subplot for Pythagorean error
            fig.plotDataVsTime(nonan, ['# count','pyth_err'], err_sub, style='b.-') #graph Pythagorean error by time

            err_sub.set_ylim([0, sum(P)/len(P)]) #set upper limit to mean of Pythagorean error

            V = calculateUndirectedVelocity(x,y, data, nonan)
            nonan['velocity'] = V #again, because nans are excluded
            globalVmax = 10.*sum(V)/len(V)
            nonan['# count_v'] = nonan['# count'][1:] #there is one fewer data point in velocity
            vel_sub = fig.subs['velocity_sub'] #get only the subplot for velocity
            vel_sub.set_ylim([0, globalVmax])  #set upper limit to mean of velocity

            fig.plotDataVsTime(nonan, ['# count_v','velocity'], vel_sub, style='g-') #graph velocity

            #add cursor
            fig.addCursor('time_xy_sub', 'error_sub', self.fixationWindowSec * self.Hz)  # Add special cursor to select time window in the top-left plot

            return fig

        def calculatePythagoreanError(x,y, data, nonan): #Pythagorean error
            P = []
            pos = 0
            
            for k in range(len(nonan['time'])):
                eye_x = nonan[x][k]
                eye_y = nonan[y][k] #eye position

                while data['time'][pos] < nonan['time'][k]: #used to match data position with nonan position by time
                    pos += 1
                targ_x = data['posx'][pos]
                targ_y = data['posy'][pos] #target position
                
                err = math.sqrt( (eye_x - targ_x)**2 + \
                                 (eye_y - targ_y)**2) #Pythagorean distance between eye position and target position
                P.append(err)

            return P

        def calculateUndirectedVelocity(x,y, data, nonan): #calculate undirected velocity
            V = []
            for k in range(len(nonan['time'])-1):
                eye_x1 = nonan[x][k]
                eye_y1 = nonan[y][k]
                eye_x2 = nonan[x][k+1] #successive eye positions
                eye_y2 = nonan[y][k+1]

                distance = math.sqrt( (eye_x2-eye_x1)**2 + \
                                      (eye_y2-eye_y1)**2 ) #Pythagorean distance between successive eye positions
                timediff = nonan['time'][k+1] - nonan['time'][k] #delta time

                if timediff > 0: #sometimes a time stamp gets duplicated for some reason
                    velocity = distance / timediff #v = d/t
                else:
                    velocity = 0

                V.append(velocity)
                
            return V

        try:
            startTime = self.data['# count'][0] #initialize time range to earliest and latest times
            endTime = self.data['# count'][-1]
        except KeyError:
            startTime = 0
            endTime = len(self.data)

        figs = [] #create and keep figure(s)
        if 'left_gaze_x' in self.interests:
            figs.append( [1, startTime, endTime, 'left_gaze', 0, \
                          createFigure(['left_gaze_x','left_gaze_y'], 1)] )
        if 'right_gaze_x' in self.interests:
            figs.append( [2, startTime, endTime, 'right_gaze', 0, \
                          createFigure(['right_gaze_x','right_gaze_y'], 2)] )

        ### structure of figs
        # figs
        #   left fig
        #     1
        #     <startTime>
        #     <endTime>
        #     "left_gaze"
        #     <initial target number>
        #     figure
        #   right fig
        #     ...
        ### So the pyplot figure for the left eye is figs[0][-1][0] (or for the right eye if there is no left eye)

        def fetchDataByTime(data, attrs, startTime, endTime): #gets the data in a particular time range
            beg = 0
            end = len(data['time'])

            #finds beginning position of startTime
            while beg < len(data['time'])-1 and data['time'][beg+1] < startTime:
                beg += 1

            #finds ending position of endTime
            while end > 0 and data['time'][end-1] > endTime:
                end -= 1

            return (data[attrs[0]][beg:end+1], data[attrs[1]][beg:end+1]) #x and y in time range

        def fetchDataByRowIndex(data, attrs, RowIndex): # gets the data for a particular target point

            #finds beginning position of RowIndex in ROW_INDEX
            if RowIndex != data['ROW_INDEX'][0]:
                first = data['ROW_INDEX'].index(RowIndex)-1
            else:
                first = data['ROW_INDEX'].index(RowIndex, 2*int(self.Hz))-1
            start = first+1

            last = start + 1
            while last < len(data['ROW_INDEX']) and data['ROW_INDEX'][start] == data['ROW_INDEX'][last]: #find end of target
                last += 1

            return data[attrs[0]][first:last+1], data[attrs[1]][first:last+1], first, last #x and y after target point

        def setDataAndLimits(figure, data, RowIndex):
            t_xy_sub = figure[-1].subs['time_xy_sub'] #retrieve top left subplot
            
            # We want to select the data with ROW_INDEX == nextTarget (and perhaps another 250msec)
            (xdats, ydats, first, last) = fetchDataByRowIndex(data, [figure[3]+'_x',figure[3]+'_y'],
                                                         RowIndex) #re-get the data

            trace = figure[-1].lines['trace']
            (xdats, ydats) = zip(*filter(lambda t: not( math.isnan(t[0]) or math.isnan(t[1])), zip(xdats,ydats))) #Python magic to filter out 'nan's
                        #in essence, ([1,2,nan,nan,5], [6,nan,8,nan,19]) -> ([1,5], [6,9])
            trace.set_xdata(xdats) #update x and y data of eye trace
            trace.set_ydata(ydats)

            sS2 = first+2
            currTarget = figure[-1].lines['currTarget'] #set the position of the red target x
            currTarget.set_xdata( [data['posx'][sS2]] )
            currTarget.set_ydata( [data['posy'][sS2]] )

            startSample = data['# count'][first] #convert from position to sample
            endSample = data['# count'][last]
            t_xy_sub.set_xlim(startSample, endSample)
            
            t_xy_sub.set_title('Target #' + str(figure[4]+1) + '        ' + figure[3][:-5] + ' eye') #set the title

            figure[1] = startSample #new time (sample) range is now in effect
            figure[2] = endSample

            vel_sub = figure[-1].subs['velocity_sub'] #retrieve velocity subplot
            vel_sub.set_ylim(0,globalVmax)


        for figure in figs:
            setDataAndLimits(figure, self.data, self.targetList[figure[4]]) #set the 2D trace and x-axis limits for first target

        plt.draw()

        def defineStatFunctions():

            clean = lambda X: list(filter(lambda x: not math.isnan(x), X)) #cleans out the nans

            #if the list is empty, these functions will return nan
            mean = lambda X: float("nan") if len(X)==0 else sum(clean(X))/len(clean(X))
            median = lambda X: float("nan") if len(X)==0 else np.median(clean(X))
            min2 = lambda X: float("nan") if len(X)==0 else min(X)
            max2 = lambda X: float("nan") if len(X)==0 else max(X)
            
            def stddev(X):
                if len(X)<=1: return float("nan")
                xbar=mean(X); return math.sqrt( mean([(x-xbar)**2 for x in X]) )
            def mode(X):
                if len(X)==0: return float("nan")
                X = [round(x,1) for x in clean(X)]
                X.sort()
                Y = [X[i+1]-X[i] for i in range(len(X)-1)]
                
                m = 0
                n = 0
                z = X[0]
                
                for j in range(len(Y)):
                    if Y[j] == 0:
                        n += 1
                        if n > m:
                            m = n
                            z = X[j]
                    elif Y[j] != 0:
                        if n > m:
                            m = n
                            z = X[j-1]
                        n = 0

                return z

            self.functions = [mean, median, mode, stddev, min2, max2]
        defineStatFunctions()


        def updateDisplayByTarget(event):

            global readyForClick
            clean = lambda X: list(filter(lambda x: not math.isnan(x), X)) #cleans out the nans
            dist = lambda x1,y1, x2,y2: math.sqrt( (x2-x1)**2+(y2-y1)**2 )

            for figure in figs:
                if figure[-1].fig.canvas == event.canvas and readyForClick: #meaning I clicked in this figure
                    readyForClick = False

                    #update eye trace, if needed
                    t_xy_sub = figure[-1].subs['time_xy_sub'] #retrieve top left subplot

                    cursor = figure[-1].widgets['time_xy_sub_cursor']
                    cursorPosition = cursor.mouseTimeVal
                    qualityMetric = cursor.qualityMetric
                    lQT = 0
                    confirmClick = cursor.confirmClick

                    if figure[-1].subs["time_xy_sub"] == event.inaxes:  # If the mouse_click was in the upper-left subplot

                        truePos = self.data['# count'].index( int(round(cursorPosition)) )

                        if cursor.clicks == 1:
                            cursorPosition = max([cursorPosition, cursor.aS])
                        elif cursor.clicks == 2:
                            cursorPosition = min([max([cursorPosition, cursor.aS]), cursor.aE - self.fixationWindowSec*self.Hz])
                            
                        
                        beg = self.data['# count'].index( int(round(cursorPosition)) )
                        end = int(round(beg + self.fixationWindowSec * self.Hz))
                        

                        if time.clock()-cursor.clickTime > cursor.clickDelay and (qualityMetric > lQT) or (qualityMetric <= lQT and confirmClick == True):
                            cursor.clickTime = time.clock()

                            if cursor.clicks == 0: #acceptable start
                                cursor.aS = beg
                                cursor.acceptableStart = self.data['time'][beg]
                                cursor.aS_quality = qualityMetric
                                
                                cursor.ly_aS.set_xdata(beg)
                                cursor.ly_aS_2.set_xdata(beg)
                                cursor.clicks += 1
                                cursor.confirmClick = False
                                
                            elif cursor.clicks == 1: #acceptable end
                                cursor.aE = beg
                                cursor.acceptableEnd = self.data['time'][beg]
                                cursor.aE_quality = qualityMetric

                                cursor.ly_aE.set_xdata(beg)
                                cursor.ly_aE_2.set_xdata(beg)
                                cursor.clicks += 1
                                cursor.confirmClick = False
                                
                            elif cursor.clicks == 2 and (cursor.aS <= truePos <= cursor.aE or cursor.durTooSmall): #window selection

                                if cursor.durTooSmall:
                                    cursor.wS = end
                                    cursor.wE = beg #swapping beg and end causes the later list slice to result in an empty list
                                    cursor.windowStart = float("nan")
                                    cursor.windowEnd = float("nan")
                                    cursor.wSE_quality = -1 #float("nan")
                                    cursor.durTooSmall = False
                                else:
                                    cursor.wS = beg
                                    cursor.wE = end
                                    cursor.windowStart = self.data['time'][beg]
                                    cursor.windowEnd = self.data['time'][end]
                                    cursor.wSE_quality = qualityMetric
                                    
                                cursor.clicks += 1
                                cursor.confirmClick = False

                            
                        elif qualityMetric <= lQT and confirmClick == False:
                            cursor.confirmClick = True
                            

                        if cursor.clicks == 3:
                            cursor.clicks = 0

                            start = self.data['# count'].index( int(round(figure[1]+1)) )
                            targetPos = (targetX, targetY) = self.data['posx'][beg], self.data['posy'][beg]

                            #calculate statistics
                            r_beg = cursor.aS
                            r_end = cursor.aE
                            w_beg = cursor.wS
                            w_end = cursor.wE

                            r_xdats = clean( self.data[figure[3]+'_x'][r_beg:r_end+1] )
                            r_ydats = clean( self.data[figure[3]+'_y'][r_beg:r_end+1] )
                            w_xdats = clean( self.data[figure[3]+'_x'][w_beg:w_end+1] )
                            w_ydats = clean( self.data[figure[3]+'_y'][w_beg:w_end+1] )

                            datsList = []

                            for span in [[r_xdats,r_ydats], [w_xdats,w_ydats]]:
                                for i,dats in enumerate(span):
                                    datsList.append(dats)
                                    datsList.append([d-targetPos[i] for d in dats])

                                datsList.append( clean([ dist(targetX, targetY, *s) for s in zip(*span) ]) )

                            statArray = [["{:.3f}".format( func(dats) ) for func in self.functions] for dats in datsList ]
                            
                            #writing out to csv file
                            outList = [self.coder, # Coder ID ('anon' default)
                                       self.fileName, # File data read from
                                       figure[3], # 'right_gaze' or 'left_gaze'

                                       #target info
                                       self.targetList[figure[4]], # Which target?
                                       "{:.3f}".format( targetX ),
                                       "{:.3f}".format( targetY ),
                                       "{:.3f}".format( self.data['time'][start] ), #target onset in seconds

                                       #acceptable start/end times, delays, and qualities, and duration
                                       "{:.3f}".format( cursor.acceptableStart ),
                                       "{:.3f}".format( cursor.acceptableStart - self.data['time'][start] ),
                                       "{:.3f}".format( cursor.aS_quality ),
                                       "{:.3f}".format( cursor.acceptableEnd ),
                                       "{:.3f}".format( cursor.acceptableEnd - self.data['time'][start] ),
                                       "{:.3f}".format( cursor.aE_quality ),
                                       "{:.3f}".format( cursor.acceptableEnd - cursor.acceptableStart ),
                                       "{:.3f}".format( len(r_xdats) ),
                                       "{:.3f}".format( len(r_ydats) ),

                                       #window start/end times, delays, quality, duration
                                       "{:.3f}".format( cursor.windowStart ),
                                       "{:.3f}".format( cursor.windowStart - self.data['time'][start] ),
                                       "{:.3f}".format( cursor.windowEnd ),
                                       "{:.3f}".format( cursor.windowEnd - self.data['time'][start] ),
                                       "{:.3f}".format( cursor.wSE_quality ),
                                       "{:.3f}".format( cursor.windowEnd - cursor.windowStart ),
                                       "{:.3f}".format( len(w_xdats) ),
                                       "{:.3f}".format( len(w_ydats) )
                                       ]

                            #add statistics to outlist
                            outList += [item   for sublist in statArray   for item in sublist]

                            self.fileWriter.writerow(outList)                            
                            self.csvfile.flush()

                            cursor.confirmClick = False
                            
                            # move on to next target
                            figure[4] += 1

                            if figure[4] > len(self.targetList)-1: # End of trial...
                                plt.close(figure[0]) #close figure if all targets have been looked at

                                if len(figs) == 0:
									#uncomment to enable email functionality
                                    #email_data(self.csvFileName, self.coder) #reached on Windows
                                    raise SystemExit #exit program when all figures are closed
                                else:
                                    return

                            setDataAndLimits(figure, self.data, self.targetList[figure[4]]) #reset 2D trace and x-axis limits

                            plt.draw()


        def closeFigure(event): #remove figure from figs
            for figure in figs:
                if not plt.fignum_exists(figure[0]): #if figure id number doesn't exist, figure doesn't exist
                    print("removing figure",figure[0])
                    figs.remove(figure) #remove from figure list

            if len(figs) == 0:

                if sys.platform == 'darwin': #only on Macs
					#uncomment to enable email functionality
                    #email_data(self.csvFileName, self.coder)
                    
                raise SystemExit #exit program if all figures have been closed

        for figure in figs: #for each figure connect events
            figure[-1].fig.canvas.mpl_connect('button_release_event', updateDisplayByTarget) #when there's a click, update trace if needed
            figure[-1].fig.canvas.mpl_connect('close_event', closeFigure) #if the 'x' button is clicked, remove figure from figs list

            figure[-1].fig.canvas.mpl_connect('motion_notify_event', figure[-1].widgets['time_xy_sub_cursor'].mouse_move)

        plt.show()

        

def email_data(dataFileName, coder):
    #imports to support email...
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.base import MIMEBase
    from email.utils import formatdate
    import email.encoders as Encoders

    msg = MIMEMultipart()
    msg['From'] = "[REDACTED]@gmail.com"
    msg['To'] = "[REDACTED]+"+coder+"@gmail.com" #replace with your own email
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = coder+'; version ' + VERSION_NUMBER

    msg.attach( MIMEText('Data file: '+dataFileName+ '; version ' + VERSION_NUMBER) )

    f = dataFileName
    part = MIMEBase('application', "octet-stream")
    part.set_payload( open(f,"rb").read() )
    Encoders.encode_base64(part)
    part.add_header('Content-Disposition', 'attachment; filename="%s"' % os.path.basename(f))
    msg.attach(part)

    print("Sending email...")

    smtp = smtplib.SMTP("smtp.gmail.com:587")
    smtp.starttls()
    smtp.login("[REDACTED]@gmail.com", "[REDACTED]") #email and password redacted for security; use yours
    smtp.sendmail(msg['From'], msg['To'], msg.as_string())
    smtp.close()

    print("Email sent!")
    

def run(name, coder='anon', fWS=0.100, targets=[]):

    myEyeDataPlot = EyeDataPlot(name, coder, targets,
                                targetDuration=1.000,
                                timeAfterTarget=0,
                                fixationWindowSec=fWS) #reads data

    try:
        myEyeDataPlot.makeFigs() #makes the figures

    except SystemExit: #normal execution exit
        return
    #except KeyboardInterrupt: #Ctrl+C
    #    raise KeyboardInterrupt
    except Exception as error: #all other exceptions
        e = sys.exc_info()[0]
        print( "Error: %s" % e )
        raise error

def run2(filepath, coder='anon'):

    if sys.version_info[0] == 2:
        strfunc = unicode
    else:
        strfunc = str #another instance where Python 3 merged functions

    with open(filepath, 'r') as f:
        lines = f.read().splitlines()
        coder, folderpath = lines[0].split(',')

        for L in lines[1:]:
            Lsplit = L.split(',')
            filename = Lsplit[0]
            fixationWindowWidth = float(Lsplit[1])

            if Lsplit[2] == 'r': #random mode
                if len(Lsplit) > 3 and strfunc(Lsplit[3]).isnumeric():
                    n = int(Lsplit[3])

                    if len(Lsplit) > 4 and strfunc(Lsplit[4]).isnumeric():
                        seed = int(Lsplit[4])
                    else:
                        seed = 0
                        
                else:
                    n = 49

                import random
                random.seed(seed)

                targets = list(range(0,49))
                random.shuffle(targets)
                targets = targets[:n]

            else:
                targets = [int(t) for t in Lsplit[2:]]
                
            #print(' ',filename,'\t',targets)
            run(folderpath+filename, coder, fixationWindowWidth, targets)

def run3():    
    import os.path

    if sys.platform == 'win32' and not os.path.isfile("codedFiles.txt"):
        #a Windows .exe opens up a terminal that can be used for input/output
        #a Mac .app does not, so this portion cannot be used on a Mac

        if sys.version_info[0] == 2:
            inputFunc = raw_input
        else:
            inputFunc = input #Python 3's input == Python 2's raw_input

        coderName = inputFunc("Please enter your initials: ")
            
        with open("codedFiles.txt", 'w') as file: #initialize codedFiles with the coder's initials
            file.write(coderName+'\n')

    with open("codedFiles.txt", 'r') as doneFileList: #this file stores which data files have already been coded
        lines = doneFileList.read().splitlines()

        coder = lines[0] #first line = coder's initials
        doneFiles = lines[1:] if len(lines) > 1 else [] #initializes the list of done file names

    with open("dataFileList.txt", 'r') as dataFileList: #this file stores the name and parameters for each data file of interest
        files = dataFileList.read().splitlines()
        
        for line in files:
            if line.split(',')[0] not in doneFiles: #looks for the first file name that hasn't already been coded
                #print(line)
                break

        if line != files[-1] or line.split(',')[0] not in doneFiles: #one has been found
            
            with open("inputFile.txt", 'w') as inputFile: #creates input file for passing to run2
                inputFile.write(coder+',Data files/\n')
                inputFile.write(line+'\n')

            #disable the following two lines if you want to repeatedly test the program
            with open("codedFiles.txt", 'a') as doneFileList: #adds file name to list of done file names
                doneFileList.write(line.split(',')[0]+'\n')

            #print("Running the program on {}".format(line.split(',')[0]))
            run2("inputFile.txt") #runs the program on that data file

        else: #all data files have already been done

            #create and email compendium file if needed
            if not os.path.isfile("compendium_"+coder+".csv"):
                print("Creating compendium...")
                allFileNames = os.listdir('Data files')
                allCSVFiles = list(filter(lambda n: n[-4:]=='.csv' and n[-21]=='_', allFileNames)) #also excludes copies
                nameDate = [[filename[:-21],filename[-21:]] for filename in allCSVFiles]
                nameDate.sort(key=lambda x:x[1], reverse=True)

                usedNames = []
                useFileList = []
                for name, date in nameDate:
                    if name.count('_') and name[:name.index('_')] not in usedNames:
                        usedNames.append(name[:name.index('_')])
                        useFileList.append(name+date)

                with open("compendium_"+coder+".csv", 'a') as outfile:
                    for filename in useFileList:
                        print(filename)
                        outfile.write( open('Data files/'+filename,'r').read()+'\n' )

				#uncomment to enable email functionality
                #email_data("compendium_"+coder+".csv", useFileList[0].split('_')[1])

            #pop up a window telling the user that they're done
            fig = plt.figure()
            fig.text(0.5,0.5,
                        "You have coded all data files.\nThank you for participating.\n\nClick anywhere to exit.",
                        fontsize=20, horizontalalignment='center', verticalalignment='center')

            fig.canvas.mpl_connect('button_release_event', lambda fig: plt.close())
            plt.show()


if __name__ == '__main__':
    #email_data("codedFiles.txt","LTB") #uncomment to test email functionality only
    #raise SystemExit

    run3()
