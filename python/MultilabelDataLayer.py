# imports
import json
import time
import pickle
import scipy.misc
import skimage.io
import caffe
import random

import numpy as np
import os.path as osp
import sys
import cv2

from xml.dom import minidom
from random import shuffle
from threading import Thread
from PIL import Image

import scipy.io as sio

from DataTransformer import DataTransformer
TRAIN = 0

class Multilabel_Data_Layer(caffe.Layer):

    """
    This is a simple synchronous datalayer for training a multilabel deep model;
    Each label is represented with an image. The data augmentation is performed on the fly.
    """

    def setup(self, bottom, top):

        self.top_names = ['data', 'label_depth']

        # === Read input parameters ===

        # params is a python dictionary with layer parameters.
        params = eval(self.param_str)

        # Check the parameters for validity.
        check_params(params)

        # store input as class variables
        self.batch_size = params['batch_size']
        
        self.root_dir = params['root_dir']
        
        self.list_file = params['list_file']
        
        self.crop_size = params['crop_size'];
        
        self.scale_factors = params['scale_factors']
        
        self.mean_values = params['mean_values']
        
        #And some top blobs, depending on the phase
        if self.phase == TRAIN and len(top) != 2:
            raise Exception("Wrong number of top blobs (img, depth)")
         
        # === reshape tops ===
        # using crop_size to crop from input color images
        if self.crop_size:
            top[0].reshape(self.batch_size, 3, self.crop_size[0], self.crop_size[1])
            # depth
            top[1].reshape(self.batch_size, 1, self.crop_size[0], self.crop_size[1])
        else:
            print "crop_size must be specified!"
            sys.exit(0)
            
        #read the training txt file to get the name list of training samples.
        self.list_samples = []
        for line in open(self.list_file):
            sample_names = line.rstrip('\n').split(' ');
            self.list_samples.append(sample_names);
                       
        # shuffle
        if params['shuffle'] == True:
            shuffle(self.list_samples);
        
        params['list_samples'] = self.list_samples; 
        
        # Create a batch loader to load the images.
        self.batch_loader = BatchLoader(params, None)
                
        print_info("MultilabelDataLayer", params)

    def forward(self, bottom, top):
        """
        Load data
        """
        for itt in range(self.batch_size):
            # Use the batch loader to load the next image.
            im, label_depth = self.batch_loader.load_next_sample()
            #sio.savemat('im.mat', {'im': im});
            #sio.savemat('label_seg.mat', {'label_seg': label_seg});
            #sio.savemat('label_depth.mat', {'label_depth': label_depth});
            #sio.savemat('label_contour', {'label_contour': label_contour});
            #sio.savemat('label_surface', {'label_surface': label_surface});
            #for debuging
            #print label_seg.max()
            #print label_seg.min()
            #print np.unique(label_seg)
            #print im.shape
            # im = im.transpose(1,2,0);
            # label_seg = label_seg.reshape(label_seg.shape[1], label_seg.shape[2]);
            # label_depth = label_depth.reshape(label_depth.shape[1], label_depth.shape[2]);
            # cv2.imwrite('/home/dxu/multiTaskSegmentation/im.png', im.astype(np.uint8));
            # cv2.imwrite('/home/dxu/multiTaskSegmentation/label_seg.png', label_seg.astype(np.uint8));
            # label_depth = (label_depth / float(label_depth.max()) * 255).astype(np.uint8);
            # cv2.imwrite('/home/dxu/multiTaskSegmentation/label_depth.png', label_depth)
            
            # Add directly to the caffe data layer            
            top[0].data[itt, ...] = im
            top[1].data[itt, ...] = label_depth

    def reshape(self, bottom, top):
        """
        There is no need to reshape the data, since the input is of fixed size
        (rows and columns)
        """
        pass

    def backward(self, top, propagate_down, bottom):
        """
        These layers does not back propagate
        """
        pass

class BatchLoader(object):

    """
    This class abstracts away the loading of images.
    Images can either be loaded singly, or in a batch. The latter is used for
    the asyncronous data layer to preload batches while other processing is
    performed.
    """

    def __init__(self, params, result):
        # initialize
        self._cur = 0  # current image        
        self.root_dir = params['root_dir'];
        self.list_samples = params['list_samples'];
        self.scale_factors = params['scale_factors'];
        self.mean_values = params['mean_values'];
        self.mirror = params['mirror'];
        self.crop_size = params['crop_size'];
        
        self.transformer = DataTransformer(self.mean_values, self.crop_size);
        
        print "BatchLoader initialized with {} images".format(
            len(self.list_samples))

    def load_next_sample(self):
        """
        Load the next image in a batch.
        """
        
        # Did we finish an epoch?
        if self._cur == len(self.list_samples):
            self._cur = 0
            shuffle(self.list_samples)

        # Load rgb and its different types of gt from one sample
        image_file_name = self.list_samples[self._cur][0];
        depth_file_name = self.list_samples[self._cur][1];
        
        # determine if the file exists ...
        if not osp.isfile(osp.join(self.root_dir, image_file_name)):
            print('The file {} doesnot exist!!!'.format(osp.join(self.root_dir, image_file_name)));
            sys.exit(0);
        
        # start to read samples ...
        img = cv2.imread(osp.join(self.root_dir, image_file_name), 1);
        #rotate label, start label from 0 and change the void label from 0 to 255 (to ingore)     
        depth = cv2.imread(osp.join(self.root_dir, depth_file_name), -1);

        # do a simple horizontal flip as data augmentation       
        if self.mirror == True:
            flip = np.random.choice(2)*2-1
            img = img[:, ::flip]
            depth = depth[:, ::flip]
        
        # randomly pick a scale from scale factors
        scale_num = len(self.scale_factors)
        self.scale = self.scale_factors[np.random.choice(scale_num)]

        self._cur += 1
        return self.transformer.preprocess(img, depth, self.scale);

def check_params(params):
    """
    A utility function to check the parameters for the data layers.
    """
    assert 'split' in params.keys(
    ), 'Params must include split (train, val, or test).'

    required = ['batch_size', 'root_dir', 'list_file', 'scale_factors', 'mean_values', 'root_dir', 'list_file']
    for r in required:
        assert r in params.keys(), 'Params must include {}'.format(r)

def print_info(name, params):
    """
    Output some info regarding the class
    """
    print "{} initialized for split: {}, with bs: {}, image cropped to size: {}.".format(
        name,
        params['split'],
        params['batch_size'],
        params['crop_size'])
