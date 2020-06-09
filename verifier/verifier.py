"""
Module wrapping up VideoAssetProcessor class in order to serve as interface for
CLI and API.
It manages pre-verification and tamper verfication of assets
"""

import uuid
import time
import json
import tarfile
import os
import sys
import urllib
import subprocess
from joblib import load
import pickle
import numpy as np
import cv2
from catboost import CatBoostClassifier
from scipy.io import wavfile

sys.path.insert(0, 'scripts/asset_processor')

from video_asset_processor import VideoAssetProcessor


def pre_verify(source, rendition):
	"""
	Function to verify that rendition conditions and specifications
	are met as prescribed by the Broadcaster
	"""
	# Extract data from video capture
	video_file, audio_file, video_available, audio_available = retrieve_video_file(rendition['uri'])
	rendition['video_available'] = video_available
	rendition['audio_available'] = audio_available

	if video_available:
		# Check that the audio exists
		if audio_available and source['audio_available']:

			_, source_file_series = wavfile.read(source['audio_path'])
			_, rendition_file_series = wavfile.read(audio_file)

			try:
				# Compute the Euclidean distance between source's and rendition's signals
				rendition['audio_dist'] = np.linalg.norm(source_file_series - rendition_file_series)
			except:
				# Set to negative to indicate an error during audio comparison
				# (matching floating-point datatype of Euclidean distance)
				rendition['audio_dist'] = -1.0
			# Cleanup the audio file generated to avoid cluttering
			os.remove(audio_file)

		rendition_capture = cv2.VideoCapture(video_file)
		fps = int(rendition_capture.get(cv2.CAP_PROP_FPS))
		frame_count = int(rendition_capture.get(cv2.CAP_PROP_FRAME_COUNT))
		height = float(rendition_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
		width = float(rendition_capture.get(cv2.CAP_PROP_FRAME_WIDTH))

		rendition_copy = rendition.copy()
		rendition['path'] = video_file

		# Create dictionary with passed / failed verification parameters

		for key in rendition_copy:
			if key == 'resolution':
				rendition['resolution']['height_pre_verification'] = height / float(rendition['resolution']['height'])
				rendition['resolution']['width_pre_verification'] = width / float(rendition['resolution']['width'])

			if key == 'frame_rate':
				rendition['frame_rate'] = 0.99 <= fps / float(rendition['frame_rate']) <= 1.01

			if key == 'bitrate':
				# Compute bitrate
				duration = float(frame_count) / float(fps)  # in seconds
				bitrate = os.path.getsize(video_file) / duration
				rendition['bitrate'] = bitrate == rendition['bitrate']

			if key == 'pixels':
				rendition['pixels_pre_verification'] = float(rendition['pixels']) / frame_count * height * width

	return rendition


def verify(source_uri, renditions, do_profiling, max_samples, model_dir, model_name, video_asset_processor=VideoAssetProcessor, debug=False, use_gpu=False):
	"""
	Function that returns the predicted compliance of a list of renditions
	with respect to a given source file using a specified model.
	"""

	total_start = time.clock()
	total_start_user = time.time()

	source_video, source_audio, video_available, audio_available = retrieve_video_file(source_uri)

	if video_available:
		# Prepare source and renditions for verification
		source = {'path': source_video,
				  'audio_path': source_audio,
				  'video_available': video_available,
				  'audio_available': audio_available,
				  'uri': source_uri}

		# Create a list of preverified renditions
		pre_verified_renditions = []
		for rendition in renditions:
			pre_verification = pre_verify(source, rendition)
			if rendition['video_available']:
				pre_verified_renditions.append(pre_verification)

		# Cleanup the audio file generated to avoid cluttering
		if os.path.exists(source['audio_path']):
			os.remove(source['audio_path'])

		# Configure model for inference
		scaler_type = 'StandardScaler'
		learning_type = 'UL'
		loaded_model = CatBoostClassifier()
		loaded_model.load_model('{}/{}'.format(model_dir, model_name))

		# Remove non numeric features from feature list
		non_temporal_features = ['attack_ID', 'title', 'attack', 'dimension', 'size', 'size_dimension_ratio']
		metrics_list = []
		model_features = ['temporal_gaussian_difference-mean',
						   'size_dimension_ratio',
						   'temporal_dct-mean',
						   'temporal_gaussian_mse-mean',
						   'temporal_threshold_gaussian_difference-mean']
		for metric in model_features:
			if metric not in non_temporal_features:
				metrics_list.append(metric.split('-')[0])

		# Initialize times for assets processing profiling
		start = time.clock()
		start_user = time.time()

		# Instantiate VideoAssetProcessor class
		asset_processor = video_asset_processor(source,
												pre_verified_renditions,
												metrics_list,
												do_profiling,
												max_samples,
												None,
												debug,
												use_gpu)

		# Record time for class initialization
		initialize_time = time.clock() - start
		initialize_time_user = time.time() - start_user

		# Register times for asset processing
		start = time.clock()
		start_user = time.time()

		# Assemble output dataframe with processed metrics
		metrics_df, pixels_df, dimensions_df = asset_processor.process()

		# Record time for processing of assets metrics
		process_time = time.clock() - start
		process_time_user = time.time() - start_user

		# Normalize input data using the associated scaler
		x_renditions = np.asarray(metrics_df[model_features])

		# Make predictions for given data
		start = time.clock()
		y_pred = loaded_model.predict_proba(x_renditions)[:, 1]
		prediction_time = time.clock() - start

		# Add predictions to rendition dictionary
		i = 0
		for _, rendition in enumerate(renditions):
			if rendition['video_available']:
				rendition.pop('path', None)
				rendition['tamper'] = np.round(y_pred[i], 6)
				# Append the post-verification of resolution and pixel count
				if 'pixels' in rendition:
					rendition['pixels_post_verification'] = float(rendition['pixels']) / pixels_df[i]
				if 'resolution' in rendition:
					rendition['resolution']['height_post_verification'] = float(rendition['resolution']['height']) / int(dimensions_df[i].split(':')[0])
					rendition['resolution']['width_post_verification'] = float(rendition['resolution']['width']) / int(dimensions_df[i].split(':')[1])
				i += 1

		if do_profiling:
			print('Features used:', model_features)
			print('Total CPU time:', time.clock() - total_start)
			print('Total user time:', time.time() - total_start_user)
			print('Initialization CPU time:', initialize_time)
			print('Initialization user time:', initialize_time_user)

			print('Process CPU time:', process_time)
			print('Process user time:', process_time_user)
			print('Prediction CPU time:', prediction_time)

	return renditions


def retrieve_model(uri):
	"""
	Function to obtain pre-trained model for verification predictions
	"""

	model_dir = '/tmp/model'
	model_file = uri.split('/')[-1]
	# Create target Directory if don't exist
	if not os.path.exists(model_dir):
		os.mkdir(model_dir)
		print('Directory ', model_dir, ' Created ')
		print('Model download started!')
		filename, _ = urllib.request.urlretrieve(uri,
												 filename='{}/{}'.format(model_dir, model_file))
		print('Model downloaded')
		try:
			with tarfile.open(filename) as tar_f:
				tar_f.extractall(model_dir)
				return model_dir, model_file
		except Exception:
			return 'Unable to untar model'
	else:
		print('Directory ', model_dir, ' already exists, skipping download')
		return model_dir, model_file


def retrieve_video_file(uri):
	"""
	Function to obtain a path to a video file from url or local path
	"""
	video_file = ''
	audio_file = ''
	video_available = True
	audio_available = True

	if 'http' in uri:
		try:
			file_name = '/tmp/{}'.format(uuid.uuid4())

			print('File download started!', flush=True)
			video_file, _ = urllib.request.urlretrieve(uri, filename=file_name)

			print('File downloaded to {}'.format(video_file), flush=True)
		except:
			print('Unable to download video file', flush=True)
			video_available = False
	else:
		if os.path.isfile(uri):
			video_file = uri

			print('Video file {} available in file system'.format(video_file), flush=True)
		else:
			video_available = False
			print('File {} NOT available in file system'.format(uri), flush=True)

	if video_available:
		try:
			audio_file = '{}_audio.wav'.format(video_file)
			subprocess.call(['ffmpeg',
							 '-y',
							 '-hide_banner',
							 '-i',
							 video_file,
							 '-vn',
							 '-acodec',
							 'pcm_s16le',
							 audio_file], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
		except:
			print('Could not extract audio from video file {}'.format(video_file))
			audio_available = False
		if os.path.isfile(audio_file):
			print('Audio file {} available in file system'.format(audio_file), flush=True)
		else:
			print('Audio file {} NOT available in file system'.format(audio_file), flush=True)
			audio_available = False

	return video_file, audio_file, video_available, audio_available
