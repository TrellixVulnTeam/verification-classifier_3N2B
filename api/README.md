# REST HTTP API INSTRUCTIONS

Description of this functionality can be found in [this](https://github.com/livepeer/verification-classifier/issues/40) github issue.

## 1.- Build the image and create a container

To build the image and create a container, we have to run the following bash script located in the root of the project:

```
./launch_api.sh
```

This will create a Docker image based on `python3` and adds the needed python dependencies.
This image basically wraps a Flask http server around the verifier.py script.

## 2.- Usage

Once the Docker container is running, a Flask HTTP server will made available in the port 5000.

### Parameters

*Object* - The verification request object

    *source*: string - The URI that can be used to download the input segment. The verifier can infer how to download the segment based on the schema of the URI (i.e. download via HTTPS if the URI has a https:// prefix). If the verifier does not support the schema of the URI or if it is missing, the verifier will look for the data locally

    *renditions*: array Rendition - An array of rendition objects that contain rendition URIs that can be used to download the rendition segment data. The rendition URIs are nested in a object to allow for future addition of fields that can indicate expected values for pre-verification checks (i.e. expected bitrate, framerate, resolution, etc.)

### Example Parameters

params: [{
    "source": "http://127.0.0.1/stream/abcd/5.ts",
    "renditions": [
        "uri": "http://127.0.0.1/stream/abcd/P720p30fps4x3/5.ts",
        "uri": "http://127.0.0.1/stream/abcd/P720p60fps16x9/5.ts"
    ],
    "model": "http://127.0.0.1/model/verification.tar.gz"
}]

### Returns

An object that indicates whether each rendition passed/failed verification.

### Example

A sample call to the API is provided below:

*Request (remote assets)*
```

curl localhost:5000/verify -d '{"source": "https://storage.googleapis.com/livepeer-verifier-originals/-3MYFnEaYu4.mp4", 

                                "renditions": [
                                                "https://storage.googleapis.com/livepeer-verifier-renditions/1080p_black_and_white/-3MYFnEaYu4.mp4", 
                                                "https://storage.googleapis.com/livepeer-verifier-renditions/720p_watermark/-3MYFnEaYu4.mp4"
                                               ], 

                                "model": "https://storage.googleapis.com/verification-models/verification.tar.xz"}' 

                                -H 'Content-Type: application/json'
```
*Response (remote assets)*
```
Results: [{'https://storage.googleapis.com/livepeer-verifier-renditions/1080p_black_and_white/-3MYFnEaYu4.mp4': -1}, 
          {'https://storage.googleapis.com/livepeer-verifier-renditions/720p_watermark/-3MYFnEaYu4.mp4': -1}]
```

*Request (local assets)*
```

curl localhost:5000/verify -d '{"source": "stream/sources/-3MYFnEaYu4.mp4", 

                                "renditions": [
                                                "stream/1080p_black_and_white/-3MYFnEaYu4.mp4", 
                                                "stream/720p_watermark/-3MYFnEaYu4.mp4"
                                               ], 

                                "model": "https://storage.googleapis.com/verification-models/verification.tar.xz"}' 

                                -H 'Content-Type: application/json'
```
*Response (local assets)*
```
Results: [{'stream/1080p_black_and_white/-3MYFnEaYu4.mp4': -1}, 
          {'stream/720p_watermark/-3MYFnEaYu4.mp4': -1}]
```