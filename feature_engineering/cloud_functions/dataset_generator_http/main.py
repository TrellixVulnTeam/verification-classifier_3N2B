'''
Main function to be called from GCE's cloud function
This function is in charge of adding training data to
the datastore for later generation of models and feature study
'''

import sys
import os
import time
import urllib
import numpy as np

from google.cloud import datastore

sys.path.insert(0, 'imports')

from imports.video_asset_processor import VideoAssetProcessor

DATASTORE_CLIENT = datastore.Client()


def compute_metrics(asset, renditions):
    '''
    Function that instantiates the VideoAssetProcessor class with a list
    of metrics to be computed.
    The feature_list argument is left void as every descriptor of each
    temporal metric is potentially used for model training
    '''
    start_time = time.time()

    original_asset = asset

    max_samples = 60
    renditions_list = renditions
    metrics_list = ['temporal_difference',
                    'temporal_gaussian', 
                    'temporal_gaussian_difference', 
                    'temporal_gaussian_difference_threshold', 
                    'temporal_dct',
                    'temporal_texture',
                    'temporal_match'
                    ]

    max_samples = 30
    asset_processor = VideoAssetProcessor(original_asset, renditions_list, metrics_list, False, max_samples)

    metrics_df = asset_processor.process()

    for _,row in metrics_df.iterrows():
        line = row.to_dict()
        for column in metrics_df.columns:
            if 'series' in column:
                line[column] = np.array2string(np.around(line[column], decimals=5))
        add_asset_input(DATASTORE_CLIENT, '{}/{}'.format(row['title'],row['attack']), line)

    elapsed_time = time.time() - start_time
    print('Computation time:', elapsed_time)


def add_asset_input(client, title, input_data):
    entity_name = 'features_input_60_540'
    key = client.key(entity_name, title, namespace = 'livepeer-verifier-training')
    video = datastore.Entity(key)
    #input_data['created'] = datetime.datetime.utcnow()
    video.update(input_data)

    client.put(video)


def dataset_generator_http(request):
    """HTTP Cloud Function.
    Args:
        request (flask.Request): The request object.
        <http://flask.pocoo.org/docs/1.0/api/#flask.Request>
    Returns:
        The response text, or any set of values that can be turned into a
        Response object using `make_response`
        <http://flask.pocoo.org/docs/1.0/api/#flask.Flask.make_response>.
    """
    request_json = request.get_json(silent=True)
    request_args = request.args
  
    if request_json and 'name' in request_json:
        asset_name = request_json['name']
    elif request_args and 'name' in request_args:
        asset_name = request_args['name']

    original_bucket = 'livepeer-verifier-originals'
    renditions_bucket = 'livepeer-verifier-renditions'
    
    # Create the folder for the original asset
    local_folder = '/tmp/1080p'
    if not os.path.exists(local_folder):
        os.makedirs(local_folder)

    # Get the file that has been uploaded to GCS
    asset_path = {'path': '{}/{}'.format(local_folder, asset_name)}
    
    renditions_paths = []
    url = 'https://storage.googleapis.com/{}/{}'.format(original_bucket, asset_name)
    print('Downloading {}'.format(url))
    try:
        urllib.request.urlretrieve(url, asset_path['path'])
        renditions_paths.append({'path': asset_path['path']})
    except:
        print('Unable to download {}'.format(url))
        pass

    attacks_list = ['1080p_watermark', 
                    '1080p_watermark-345x114', 
                    '1080p_watermark-856x856', 
                    '1080p_vignette', 
                    '1080p_flip_vertical',
                    '1080p_rotate_90_clockwise',
                    '1080p_black_and_white',
                    '1080p_low_bitrate_4',
                    '1080p_low_bitrate_8',
                    '720p',
                    '720p_watermark',
                    '720p_watermark-345x114',
                    '720p_watermark-856x856',
                    '720p_vignette',
                    '720p_black_and_white',
                    '720p_low_bitrate_4',
                    '720p_low_bitrate_8',
                    '720p_flip_vertical',
                    '720p_rotate_90_clockwise',
                    '480p',
                    '480p_watermark',
                    '480p_watermark-345x114',
                    '480p_watermark-856x856',
                    '480p_vignette',
                    '480p_black_and_white',
                    '480p_low_bitrate_4',
                    '480p_low_bitrate_8',
                    '480p_flip_vertical',
                    '480p_rotate_90_clockwise',
                    '360p',
                    '360p_watermark',
                    '360p_watermark-345x114',
                    '360p_watermark-856x856',
                    '360p_vignette',
                    '360p_black_and_white',
                    '360p_low_bitrate_4',
                    '360p_low_bitrate_8',
                    '360p_flip_vertical',
                    '360p_rotate_90_clockwise',
                    '240p',
                    '240p_watermark',
                    '240p_watermark-345x114',
                    '240p_watermark-856x856',
                    '240p_vignette',
                    '240p_black_and_white',
                    '240p_low_bitrate_4',
                    '240p_low_bitrate_8',
                    '240p_flip_vertical',
                    '240p_rotate_90_clockwise',
                    '144p',
                    '144p_watermark',
                    '144p_watermark-345x114',
                    '144p_watermark-856x856',
                    '144p_vignette',
                    '144p_black_and_white',
                    '144p_low_bitrate_4',
                    '144p_low_bitrate_8',
                    '144p_flip_vertical',
                    '144p_rotate_90_clockwise',
                    ]

    for attack in attacks_list:
        remote_file = '{}/{}'.format(attack, asset_name)
        url = 'https://storage.googleapis.com/{}/{}'.format(renditions_bucket, remote_file)
        
        local_folder = '/tmp/{}'.format(attack)
        local_file = '{}/{}'.format(local_folder, asset_name)
        
        if not os.path.exists(local_folder):
            os.makedirs(local_folder)

        print('Downloading {}'.format(url))
        try:
            urllib.request.urlretrieve (url, local_file)
            renditions_paths.append({'path': local_file})
        except:
            print('Unable to download {}'.format(url))
            pass

    compute_metrics(asset_path, renditions_paths)