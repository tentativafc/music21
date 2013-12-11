# -*- coding: utf-8 -*-
#------------------------------------------------------------------------------
# Name:         reduceChords.py
# Purpose:      Tools for eliminating passing chords, etc.
#
# Authors:      Michael Scott Cuthbert
#
# Copyright:    Copyright © 2013 Michael Scott Cuthbert and the music21 Project
# License:      LGPL, see license.txt
#------------------------------------------------------------------------------

'''
Automatically reduce a MeasureStack to a single chord or group of chords.
'''

import unittest
import copy
from music21 import meter
from music21 import stream
from music21 import tie


def testMeasureStream1():
    '''
    returns a simple measure stream for testing:


    >>> s = analysis.reduceChords.testMeasureStream1()
    >>> s.show('text')
    {0.0} <music21.meter.TimeSignature 4/4>
    {0.0} <music21.chord.Chord C4 E4 G4 C5>
    {2.0} <music21.chord.Chord C4 E4 F4 B4>
    {3.0} <music21.chord.Chord C4 E4 G4 C5>
    '''
    from music21 import chord
    s = stream.Measure()
    t = meter.TimeSignature('4/4')
    c1 = chord.Chord('C4 E4 G4 C5')
    c1.quarterLength = 2.0
    c2 = chord.Chord('C4 E4 F4 B4')
    c3 = chord.Chord('C4 E4 G4 C5')
    for c in [t, c1, c2, c3]:
        s.append(c)
    return s


class ChordReducer(object):
    r'''
    A chord reducer.
    '''

    ### INITIALIZER ###

    def __init__(self):
        self.printDebug = False
        self.weightAlgorithm = self.qlbsmpConsonance
        self.maxChords = 3

    ### PRIVATE METHODS ###

    def _buildOutputMeasure(self,
        closedPosition,
        forceOctave,
        i,
        inputMeasure,
        inputMeasureReduction,
        lastPitchedObject,
        lastTimeSignature,
        ):
        outputMeasure = stream.Measure()
        outputMeasure.number = i
        #inputMeasureReduction.show('text')
        cLast = None
        cLastEnd = 0.0
        for cEl in inputMeasureReduction:
            cElCopy = copy.deepcopy(cEl)
            if 'Chord' in cEl.classes:
                if closedPosition is not False:
                    if forceOctave is not False:
                        cElCopy.closedPosition(
                            forceOctave=forceOctave,
                            inPlace=True,
                            )
                    else:
                        cElCopy.closedPosition(inPlace=True)
                    cElCopy.removeRedundantPitches(inPlace=True)
            newOffset = cEl.getOffsetBySite(inputMeasureReduction)
            # extend over gaps
            if cLast is not None:
                if round(newOffset - cLastEnd, 6) != 0.0:
                    cLast.quarterLength += newOffset - cLastEnd
            cLast = cElCopy
            cLastEnd = newOffset + cElCopy.quarterLength
            outputMeasure._insertCore(newOffset, cElCopy)
        tsContext = inputMeasure.parts[0].getContextByClass('TimeSignature')
        if tsContext is not None:
            if round(tsContext.barDuration.quarterLength - cLastEnd, 6) != 0.0:
                cLast.quarterLength += tsContext.barDuration.quarterLength - cLastEnd
        outputMeasure._elementsChanged()
        # add ties
        if lastPitchedObject is not None:
            firstPitched = outputMeasure[0]
            if lastPitchedObject.isNote and firstPitched.isNote:
                if lastPitchedObject.pitch == firstPitched.pitch:
                    lastPitchedObject.tie = tie.Tie("start")
            elif lastPitchedObject.isChord and firstPitched.isChord:
                if len(lastPitchedObject) == len(firstPitched):
                    allSame = True
                    for pitchI in range(len(lastPitchedObject)):
                        if lastPitchedObject.pitches[pitchI] != firstPitched.pitches[pitchI]:
                            allSame = False
                    if allSame is True:
                        lastPitchedObject.tie = tie.Tie('start')
        lastPitchedObject = outputMeasure[-1]
        sourceMeasureTs = inputMeasure.parts[0].getElementsByClass('Measure')[0].timeSignature
        if sourceMeasureTs != lastTimeSignature:
            outputMeasure.timeSignature = copy.deepcopy(sourceMeasureTs)
            lastTimeSignature = sourceMeasureTs
        return lastPitchedObject, lastTimeSignature, outputMeasure

    ### PUBLIC METHODS ###

    def computeMeasureChordWeights(self, measureObj, weightAlgorithm=None):
        '''
        Compute measure chord weights:

        ::

            >>> s = analysis.reduceChords.testMeasureStream1().notes
            >>> cr = analysis.reduceChords.ChordReducer()
            >>> cws = cr.computeMeasureChordWeights(s)
            >>> for pcs in sorted(cws):
            ...     print "%18r  %2.1f" % (pcs, cws[pcs])
                (0, 4, 7)  3.0
            (0, 11, 4, 5)  1.0

        Add beatStrength:

        ::

            >>> cws = cr.computeMeasureChordWeights(s,
            ...     weightAlgorithm=cr.quarterLengthBeatStrength)
            >>> for pcs in sorted(cws):
            ...     print "%18r  %2.1f" % (pcs, cws[pcs])
                (0, 4, 7)  2.2
            (0, 11, 4, 5)  0.5

        Give extra weight to the last element in a measure:

        ::

            >>> cws = cr.computeMeasureChordWeights(s,
            ...     weightAlgorithm=cr.quarterLengthBeatStrengthMeasurePosition)
            >>> for pcs in sorted(cws):
            ...     print "%18r  %2.1f" % (pcs, cws[pcs])
                (0, 4, 7)  3.0
            (0, 11, 4, 5)  0.5

        Make consonance count a lot:

        >>> cws = cr.computeMeasureChordWeights(s,
        ...     weightAlgorithm=cr.qlbsmpConsonance)
        >>> for pcs in sorted(cws):
        ...     print "%18r  %2.1f" % (pcs, cws[pcs])
             (0, 4, 7)  3.0
         (0, 11, 4, 5)  0.1
        '''
        if weightAlgorithm is None:
            weightAlgorithm = self.quarterLengthOnly
        presentPCs = {}

        self.positionInMeasure = 0
        self.numberOfElementsInMeasure = len(measureObj)

        for i, c in enumerate(measureObj):
            self.positionInMeasure = i
            if c.isNote:
                p = tuple(c.pitch.pitchClass)
            else:
                p = tuple(set([x.pitchClass for x in c.pitches]))
            if p not in presentPCs:
                presentPCs[p] = 0.0
            presentPCs[p] += weightAlgorithm(c)

        self.positionInMeasure = 0
        self.numberOfElementsInMeasure = 0

        return presentPCs

    def multiPartReduction(
        self,
        inputStream,
        maxChords=2,
        closedPosition=False,
        forceOctave=False,
        ):
        '''
        Return a multipart reduction of a stream.
        '''
        i = 0
        outputStream = stream.Part()
        gobcM = inputStream.parts[0].getElementsByClass('Measure')
        lenMeasures = len(gobcM)
        lastPitchedObject = None
        lastTimeSignature = None
        while i <= lenMeasures:
            inputMeasure = inputStream.measure(i, ignoreNumbers=True)
            if not len(inputMeasure.flat.notesAndRests):
                if not i:
                    pass
                else:
                    break
            else:
                inputMeasureReduction = self.reduceMeasureToNChords(
                    inputMeasure.chordify(),
                    maxChords,
                    weightAlgorithm=self.qlbsmpConsonance,
                    trimBelow=0.3,
                    )
                lastPitchedObject, lastTimeSignature, outputMeasure = \
                    self._buildOutputMeasure(
                        closedPosition,
                        forceOctave,
                        i,
                        inputMeasure,
                        inputMeasureReduction,
                        lastPitchedObject,
                        lastTimeSignature,
                        )
                outputStream._appendCore(outputMeasure)
            if self.printDebug:
                print i, " ",
                if i % 20 == 0 and i != 0:
                    print ""
            i += 1
        outputStream._elementsChanged()
        outputStream.getElementsByClass('Measure')[0].insert(
            0, outputStream.bestClef(allowTreble8vb=True))
        outputStream.makeNotation(inPlace=True)
        return outputStream

    def qlbsmpConsonance(self, c):
        '''
        Everything from before plus consonance
        '''
        consonanceScore = 1.0 if c.isConsonant() else 0.1
        if self.positionInMeasure == self.numberOfElementsInMeasure - 1:
            return c.quarterLength * consonanceScore  # call beatStrength 1
        return self.quarterLengthBeatStrengthMeasurePosition(c) * consonanceScore

    def quarterLengthBeatStrength(self, c):
        return c.quarterLength * c.beatStrength

    def quarterLengthBeatStrengthMeasurePosition(self, c):
        if self.positionInMeasure == self.numberOfElementsInMeasure - 1:
            return c.quarterLength  # call beatStrength 1
        else:
            return self.quarterLengthBeatStrength(c)

    def quarterLengthOnly(self, c):
        return c.quarterLength

    def reduceMeasureToNChords(
        self,
        measureObj,
        numChords=1,
        weightAlgorithm=None,
        trimBelow=0.25,
        ):
        '''
        Reduces measure to `n` chords:

        ::

            >>> s = analysis.reduceChords.testMeasureStream1()
            >>> cr = analysis.reduceChords.ChordReducer()

        Reduce to a maximum of 3 chords; though here we will only get one
        because the other chord is below the trimBelow threshold.

        ::

            >>> newS = cr.reduceMeasureToNChords(s, 3,
            ...     weightAlgorithm=cr.qlbsmpConsonance,
            ...     trimBelow=0.3)
            >>> newS.show('text')
            {0.0} <music21.chord.Chord C4 E4 G4 C5>

        ::

            >>> newS[0].quarterLength
            4.0

        '''
        from music21 import note
        if measureObj.isFlat is False:
            mObj = measureObj.flat.notes
        else:
            mObj = measureObj.notes

        chordWeights = self.computeMeasureChordWeights(mObj, weightAlgorithm)

        if numChords > len(chordWeights):
            numChords = len(chordWeights)

        sortedChords = sorted(chordWeights, key=chordWeights.get, reverse=True)
        maxNChords = sortedChords[:numChords]
        if len(maxNChords) == 0:
            r = note.Rest()
            r.quarterLength = mObj.duration.quarterLength
            for c in mObj:
                mObj.remove(c)
            mObj.insert(0, r)
            return mObj
        maxChordWeight = chordWeights[maxNChords[0]]

        trimmedMaxChords = []
        for pcTuples in maxNChords:
            if chordWeights[pcTuples] >= maxChordWeight * trimBelow:
                trimmedMaxChords.append(pcTuples)
                #print chordWeights[pcTuples], maxChordWeight
            else:
                break

        currentGreedyChord = None
        currentGreedyChordPCs = None
        currentGreedyChordNewLength = 0.0
        for c in mObj:
            if c.isNote:
                p = tuple(c.pitch.pitchClass)
            else:
                p = tuple(set([x.pitchClass for x in c.pitches]))
            if p in trimmedMaxChords and p != currentGreedyChordPCs:
                # keep this chord
                if currentGreedyChord is None and c.offset != 0.0:
                    currentGreedyChordNewLength = c.offset
                    c.offset = 0.0
                elif currentGreedyChord is not None:
                    currentGreedyChord.quarterLength = currentGreedyChordNewLength
                    currentGreedyChordNewLength = 0.0
                currentGreedyChord = c
                for n in c:
                    n.tie = None
                    if n.pitch.accidental is not None:
                        n.pitch.accidental.displayStatus = None
                currentGreedyChordPCs = p
                currentGreedyChordNewLength += c.quarterLength
            else:
                currentGreedyChordNewLength += c.quarterLength
                mObj.remove(c)
        if currentGreedyChord is not None:
            currentGreedyChord.quarterLength = currentGreedyChordNewLength
            currentGreedyChordNewLength = 0.0

        # even chord lengths...
        for i in range(1, len(mObj)):
            c = mObj[i]
            cOffsetCurrent = c.offset
            cOffsetSyncop = cOffsetCurrent - int(cOffsetCurrent)
            if round(cOffsetSyncop, 3) in [0.250, 0.125, 0.333, 0.063, 0.062]:
                lastC = mObj[i - 1]
                lastC.quarterLength -= cOffsetSyncop
                c.offset = int(cOffsetCurrent)
                c.quarterLength += cOffsetSyncop

        return mObj


#------------------------------------------------------------------------------


class Test(unittest.TestCase):

    def runTest(self):
        pass

    def testSimpleMeasure(self):
        from music21 import chord
        s = stream.Measure()
        c1 = chord.Chord('C4 E4 G4 C5')
        c1.quarterLength = 2.0
        c2 = chord.Chord('C4 E4 F4 B4')
        c3 = chord.Chord('C4 E4 G4 C5')
        for c in [c1, c2, c3]:
            s.append(c)


class TestExternal(unittest.TestCase):

    def runTest(self):
        pass

    def testTrecentoMadrigal(self):
        from music21 import corpus
        #c = corpus.parse('beethoven/opus18no1', 2).measures(1, 19)
        c = corpus.parse('PMFC_06_Giovanni-05_Donna').measures(1, 30)
        #c = corpus.parse('PMFC_06_Giovanni-05_Donna').measures(90, 118)
        #c = corpus.parse('PMFC_06_Piero_1').measures(1, 10)
        #c = corpus.parse('PMFC_06-Jacopo').measures(1, 30)
        #c = corpus.parse('PMFC_12_13').measures(1, 40)

        # fix clef
        fixClef = True
        if fixClef:
            from music21 import clef
            firstMeasure = c.parts[1].getElementsByClass('Measure')[0]
            startClefs = firstMeasure.getElementsByClass('Clef')
            if len(startClefs):
                clef1 = startClefs[0]
                firstMeasure.remove(clef1)
            firstMeasure.insert(0, clef.Treble8vbClef())

        cr = ChordReducer()
        #cr.printDebug = True
        p = cr.multiPartReduction(c, maxChords=3, closedPosition=True)
        #p = cr.multiPartReduction(c, closedPosition=True)
        c.insert(0, p)
        c.show()


#------------------------------------------------------------------------------
# define presented order in documentation

_DOC_ORDER = []

if __name__ == "__main__":
    import music21
    music21.mainTest(TestExternal)
