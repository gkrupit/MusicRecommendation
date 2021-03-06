import subprocess
from pydub import AudioSegment
import sys
import scipy.io.wavfile
import threading
from multiprocessing import Pool, pool
import multiprocessing
import wave, array, math, time, argparse, sys, numpy
from pywt import dwt
from scipy import signal
import pdb
import BPM
import itertools
import os
from functools import partial
from Chromagram import Chromagram
from ChordDetector import ChordDetector

keys = [
        'C',  'Cm',
        'Db', 'C#m',
        'D', 'Dm',
        'Eb', 'D#m',
        'E', 'Em',
        'F', 'Fm',
        'F#', 'F#m',
        'G', 'Gm',
        'Ab', 'G#m',
        'A', 'Am',
        'Bb', 'Bbm',
        'B', 'Bm'
       ]

key2val = dict()
for index, key in enumerate(keys):
    key2val[key] = index

def IsSong(song):
    if (song.endswith('.mp3')):
        return True
    return False

MusicDirectory = sys.argv[1] + '/'
if IsSong(sys.argv[1]):
    song_name = sys.argv[1]
    end_directory = song_name.rfind('/')
    MusicDirectory = sys.argv[1][ 0 : end_directory + 1 ]

class NoDaemonProcess(multiprocessing.Process):
    # make 'daemon' attribute always return False
    def _get_daemon(self):
        return False
    def _set_daemon(self, value):
        pass
    daemon = property(_get_daemon, _set_daemon)

# We sub-class multiprocessing.pool.Pool instead of multiprocessing.Pool
# because the latter is only a wrapper function, not a proper class.
class MyPool(pool.Pool):
    Process = NoDaemonProcess



#either single mp3 or directory containing multiple mp3's

class Chord:
    def __init__(self, chord, quality):
        self.freq2note = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.int2quality = ['m','','','','m',''] #int2quality = ['m','maj','sus','dominant','dim5th','aug5th'] #'' -> Major
        self.chord = chord
        self.quality = quality
        self.occurences = 0

    def SetOccurences(self, new_occ):
        self.occurences = new_occ

    def GetOccurences(self):
        return self.occurences

    def AddOccurences(self, to_add):
        self.occurences += to_add

    def UpdateWithString(self, str):
        if str.find('m') != -1: #chord is minor
            self.quality = 0
            str = str.replace('m','') #isolate chord value
        else:     #chord is not minor
            self.quality = 1

        self.chord = int(str)

    def GetChordValue(self):
        return self.chord
    def GetChordStr(self):
        return self.freq2note[self.chord]

    def GetQualityValue(self):
        return self.quality
    def GetQualityStr(self):
        return self.int2quality[self.quality]
    def __str__(self):
        return str(self.chord) + self.GetQualityStr()
    def __hash__(self):
        return hash(self.__str__())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.chord == other.GetChordValue() and self.GetQualityStr() == other.GetQualityStr()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def Translate(self, distance):
        self.chord = (self.chord + distance) % 12

def PrintChords(chords):
    for beat, chord in enumerate(chords):
        print 'beat: %d. Chord: %s' % (beat, chord)

def PrintChroma(chromagram):
    for freq, intensity in enumerate(chromagram):
        print "%s: %d" % (freq2note[freq], intensity)

def DetermineChord(sample_rate, samples_per_frame, beat_samples):
    chromagram = Chromagram(samples_per_frame, sample_rate)
    chromagram.processAudioFrame(beat_samples)
    chord = -1
    quality = ''
    if chromagram.isReady():
        chroma = chromagram.getChromagram()
        chord_detector = ChordDetector()
        chord_detector.detectChord(chroma)
        chord = chord_detector.rootNote
        quality = chord_detector.quality
    return Chord(chord, quality)

class ChordProgression:
    def __init__(self):
        self.progression = []
        self.chord_freqs = {}
        self.num_chords = 0
        self.translated = 0

    def GetProgression(self):
        return self.progression

    @staticmethod
    def PrintChordList(chords):
        for chord in chords:
            print '%s : %d' % (chord, chord.GetOccurences())

    @staticmethod
    def ConsolidateAdjacent(progression):
        consolidated = []
        for k, g in itertools.groupby(progression, lambda chord: str(chord)):
            total = 0
            for chord in list(g):
                total += chord.GetOccurences()
            chord = Chord(0,0)
            chord.UpdateWithString(k)
            chord.SetOccurences(total)
            consolidated.append(chord)
        return consolidated

    def Transpose(self, distance):
        for chord in self.progression:
            chord.Translate(distance)
        self.translated += distance
        self.UpdateDistribution()

    def RevertToOriginalKey(self):
        self.Transpose(-self.translated)

    def UpdateDistribution(self):
        self.chord_freqs = {}

        sorted_progression = sorted(self.progression, key=lambda chord: str(chord))
        consolidated = ChordProgression.ConsolidateAdjacent(sorted_progression)
        for chord in consolidated:
            self.chord_freqs[chord] = chord.GetOccurences()

    def UpdateProgression(self, new_progression):
        self.progression = new_progression
        self.num_chords = sum( [ chord.GetOccurences() for chord in new_progression ] ) # sum # of occurences of all chords
        self.UpdateDistribution()

    def RemoveExcessChords(self, valid_consistency):
        if not self.progression: #check of progression is empty
            return []

        #filter out chords below threshold for suitable number of adjacent chords
        adjusted_progression = filter(lambda chord: chord.GetOccurences() >= valid_consistency, self.progression)

        #combine adjacent duplicate chords
        adjusted_progression = ChordProgression.ConsolidateAdjacent(adjusted_progression)

        self.UpdateProgression(adjusted_progression)

        '''
        if not self.progression: #check of chords is empty
            return []
        last_seen_start = 0
        last_seen = self.progression[0]
        adjusted_progression = []

        for index, chord in enumerate(self.progression):
            if chord != last_seen:
                num_consistent = index - last_seen_start
                if num_consistent >= valid_consistency:
                    adjusted_progression += self.progression[last_seen_start : index]
                #else:
                #    print 'Removing chords within indices [%d,%d)' %(last_seen_start, index)
                last_seen_start = index
                last_seen = chord

        self.UpdateProgression(adjusted_progression)
        '''

    def GetChordDistribution(self):
        return self.chord_freqs

    def GetNumChords(self):
        return self.num_chords

    def PrintChordDistribution(self):
        distribution = self.chord_freqs
        for chord in sorted(distribution, key=distribution.get, reverse=True):
            print chord, distribution[chord], '%.3f' % (1. * distribution[chord] / self.num_chords)

    def Print(self):
        for chord in self.progression:
            print '%s : %d' % (chord, chord.GetOccurences())

    def __str__(self):
        out = ''
        for chord_num, chord in enumerate(self.progression):
            out += '%s : %d\n' % (chord, chord.GetOccurences())
        return out

class Song:
    def __init__(self, name):
        self.key_quality = ''
        self.key = -1
        self.original_key = -1
        self.name = name
        if '/' in name:
            directory_end = name.rfind('/') + 1
            self.name = self.name[ directory_end : ]
        if '_' in name:
            key_start = self.name.rfind('_') + 1
            self.key = self.name[key_start : ]
            self.original_key = self.key
            print self.key, self.name
            self.key = key2val[self.key]
            self.key_quality = 'maj' if self.key % 2 == 0 else 'min'
            print 'Key of <%s>: %d' % (self.name, self.key)

        self.CreateWav()
        self.progression = ChordProgression()
        self.bpm = -1
        self.sample_rate, self.data = scipy.io.wavfile.read(self.WAV())
        self.data = self.data[0::2] #keep left channel data
        self.Find_BPM()

    def WriteChords(self):
        with open('chords/' + self.name + '.txt','w') as f:
            f.write('%d %s %s\n' % (self.bpm, self.key_quality, self.original_key))
            for chord in self.progression.GetProgression():
                out = '%s %d\n' % (str(chord), chord.GetOccurences())
                f.write(out)

    def RemoveExcessChords(self, valid_consistency):
        self.progression.RemoveExcessChords(valid_consistency)

    def Print(self):
        print self.Name(), 'BPM:', self.BPM()
        song.PrintProgression()
        #self.PrintChordDistribution()

    def ToC(self):
        self.Transpose(-self.key//2)

    def Name(self):
        return self.name

    def BPM(self):
        return self.bpm

    def Find_BPM(self):
        print 'Finding BPM of "%s"' % self.name
        self.bpm = BPM.Find_BPM(self.WAV())
        print 'Found BPM: %f' % self.bpm

    def WAV(self):
        return MusicDirectory + self.name + '.wav'

    def MP3(self):
        return MusicDirectory + self.name + '.mp3'

    def Key(self):
        return self.key

    def CreateWav(self):
        AudioSegment.from_mp3(self.MP3()).export(self.WAV(), format='wav')

    def Transpose(self, distance):
        self.progression.Transpose(distance)
        self.key = (self.key + distance * 2) % 24

    def DetermineProgression(self):
        num_processes = 4
        num_samples = len(self.data) #- samples_per_frame

        samples_per_frame = int(60 * self.sample_rate / self.bpm) #keep track every quarter of beat to catch more chords
        frame_fraction = int(samples_per_frame / 4096)

        #split beats up into sub-beats to make chord detection more accurate (less samples per frame to analyze)
        samples_per_frame = samples_per_frame / frame_fraction
        frame_count = num_samples / samples_per_frame

        samples = self.data.tolist() #convert from numpy array to list

        '''
        Build list of lists:
        Split whole .wav sample up into subsets, determined by samples/beat
        Each beat will be analyzed one at time for its chord
        '''
        beat_sample_lists = []
        for frame in range(frame_count):
            start_sample = frame * samples_per_frame
            end_sample = start_sample + samples_per_frame
            beat_samples = samples[start_sample : end_sample]
            beat_samples = [item[0] for item in beat_samples]
            beat_sample_lists.append(beat_samples)

        if __name__ == '__main__':
            pool = Pool(processes=num_processes)
            func = partial(DetermineChord, self.sample_rate, samples_per_frame)
            chords = pool.map(func, beat_sample_lists)
            #chords = sorted(chords, key=None)
            progression = []
            for k, g in itertools.groupby(chords, None):
                k.SetOccurences(len(list(g)))
                progression.append(k) #store sublist: (chord, # of occurences of chord)
                #groups.append(list(g))      # Store group iterator as a list
            self.progression.UpdateProgression(progression)

    def PrintProgression(self):
        self.progression.Print()

    def PrintChordDistribution(self):
        self.progression.PrintChordDistribution()

    def WriteDistribution(self, offset):
        num_chords = self.progression.GetNumChords()
        file = open('Progressions/' + self.name + str((offset + self.key) % 12) + '.chords', 'w')
        distribution = self.progression.GetChordDistribution()
        file.write(str(self.key) + '\n')
        for chord in sorted(distribution, key=distribution.get, reverse=True):
            file.write(str(chord) + ',' + str(distribution[chord]) + ',' + str('%.3f' % (1. * distribution[chord] / num_chords)))
            file.write('\n')

        file.close()


'''
******************************
Begin MP3 Analysis
Analyze All MP3 files in Directory 'Music'
********************************
'''


def AnalyzeSong(song_name):
    song = Song(song_name)
    song.DetermineProgression()
    return song

def AnalyzeAllSongs(music_directory):
    song_list = []
    file_list = os.listdir(music_directory)
    for file in file_list:
        if file.endswith(".mp3"):
            song_name = file[0 : len(file) - 4]
            song_list.append(song_name)

    if __name__ == '__main__':
        num_processes = 8
        pool = MyPool(num_processes)
        song_list = pool.imap_unordered(AnalyzeSong, song_list)

    return song_list

if not IsSong(sys.argv[1]): #analyze all MP3's in directory
    song_list = AnalyzeAllSongs(sys.argv[1] + '/')

    for song in song_list:
        for offset in range(12):
            song.WriteDistribution(offset)
            song.Transpose(1)

else:
    song_name = sys.argv[1][0 : len(sys.argv[1]) - 4]
    song = AnalyzeSong(song_name)
    print 'Original Progression:'
    song.PrintProgression()
    song.RemoveExcessChords(4)
    song.ToC()
    print 'New Key:',song.Key()
    print 'After Transposing, removing excess chords (4)'
    song.PrintProgression()
    song.PrintChordDistribution()

    song.WriteChords()
    #song.RemoveExcessChords(4)
    #print 'After removing extra chords:'
    #song.PrintProgression()
    #song.Print()
    #for offset in range(12):
        #song.WriteDistribution(offset)
        #song.Transpose(1)
