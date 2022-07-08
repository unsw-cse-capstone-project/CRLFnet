#!/usr/bin/env python3

"""
Get the radar and camera messages and do Radar-camera fusion.
"""


from time import perf_counter, sleep
from pathlib import Path
import argparse
import yaml
import numpy as np

import cv2
from cv_bridge import CvBridge

import rospy
import message_filters
from sensor_msgs.msg import Image               # Camera message
from msgs.msg._MsgRadar import MsgRadar         # Radar message
from msgs.msg._MsgRadCam import MsgRadCam       # fusion message

from ..utils.poi_and_roi import radar_poi, image_roi, expand_poi, get_iou
from ..utils.yolo.yolo import YOLO
from ..utils.visualization import radar2visual  # visualized output


def iou_matching(radar_rois: np.ndarray, image_rois: np.ndarray):
    pass


def gnn(radar, image):
    pass


def kf(possible_objects, prevoius_results):
    pass


def pair_fusion(radar: MsgRadar, image: Image, camera_name='camera2'):
    # ONLY FUSE THE LEFT PAIR!!!
    global yolo
    global results
    global w2cs, c2ps

    # Separate Decection
    # acquire radar POIs (pixel coordinate) and distance
    radar_pois = radar_poi(radar.objects_left, w2cs[camera_name], c2ps[camera_name], image.width, image.height)
    radar_distances = [x.distance for x in radar.objects_left]
    # acquire image ROIs (pixel coordinate)
    image_rois = image_roi(image, yolo)

    # Fusion
    # convert the radar POIs to approximate ROIs (world coordinate -> pixel coordinate)
    radar_expanded_rois = np.array([expand_poi(p, d, image.width, image.height) for p, d in zip(radar_pois, radar_distances)], dtype=int)
    # IOU matching of radar and image ROIs
    couples_iou, unmatched_radar, unmatched_image = iou_matching(radar_expanded_rois, image_rois)
    # apply GNN to unmatched objects
    couples_gnn, residual_radar, residual_image = gnn(unmatched_radar, unmatched_image)
    # possible objects are matched objects in IOU matching and GNN and residual ones
    possible_objects = np.concatenate(couples_iou, couples_gnn, residual_radar, residual_image)
    # use Extended Kalman Filter to predict and check objects
    results = kf(possible_objects, results)

    # Publish
    print(results)


def old_fusion(radar: MsgRadar, image2: Image, image3: Image):
    global OUTPUT_DIR
    global args
    global my_timer
    global frame_counter

    global w2cs, c2ps
    global yolo
    global pub
    
    # fps
    if args.information:
        my_current = perf_counter()
        print("\033[1;36m--------------------------------\033[0m")
        print("\033[1;36mFPS:\033[0m {:.2f},\t\033[1;36mFrame:\033[0m{}".format(1.0 / (my_current - my_timer), frame_counter))
        my_timer = my_current

    # Convert messages to POIs and ROIs
    # get Radar POIs
    radar_pois_left = radar_poi(radar.objects_left, w2cs['camera2'], c2ps['camera2'], image2.width, image2.height)
    radar_pois_right = radar_poi(radar.objects_right, w2cs['camera3'], c2ps['camera3'], image3.width, image3.height)
    # off-YOLO mode
    if args.off_yolo:
        # save radar
        np.savetxt(str(OUTPUT_DIR.joinpath("L{:04d}.txt".format(frame_counter))), radar_pois_left, fmt='%d')
        np.savetxt(str(OUTPUT_DIR.joinpath("R{:04d}.txt".format(frame_counter))), radar_pois_right, fmt='%d')
        # save image
        left_image = CvBridge().imgmsg_to_cv2(image2, 'bgr8')
        cv2.imwrite(str(OUTPUT_DIR.joinpath("L{:04d}.jpg".format(frame_counter))), left_image)
        right_image = CvBridge().imgmsg_to_cv2(image3, 'bgr8')
        cv2.imwrite(str(OUTPUT_DIR.joinpath("R{:04d}.jpg".format(frame_counter))), right_image)
        print("\033[0;32mSaved radar POIs and images of frame {}.\033[0;32m sucessfully.\033[0m".format(frame_counter))
        sleep(1 / args.fps)
        frame_counter += 1
        return 
    # get Image ROIs
    image_rois_left  = image_roi(image2, yolo=yolo)
    image_rois_right = image_roi(image3, yolo=yolo)
    # print POIs and ROIs
    if args.information:
        print("\033[1;36mDetailed POI / ROI Information:\033[0m")
        print("Left Radar POIs:")
        for p in radar_pois_left:
            print("\t({},\t{})".format(p[0], p[1]))
        print("Right Radar POIS:")
        for p in radar_pois_right:
            print("\t({},\t{})".format(p[0], p[1]))
        print("Left Image ROIs:")
        for p in image_rois_left:
            print("\t({},\t{},\t{},\t{}),\t{}".format(p[0], p[1], p[2], p[3], p[4]))
        print("Right Image ROIs:")
        for p in image_rois_right:
            print("\t({},\t{},\t{},\t{}),\t{}".format(p[0], p[1], p[2], p[3], p[4]))

    # fusion
    # detection flags
    radar_left  = len(radar_pois_left)
    image_left  = len(image_rois_left)
    radar_right = len(radar_pois_right)
    image_right = len(image_rois_right)
    match_left  = 0
    match_right = 0
    # left
    for rpoi in radar_pois_left:
        for iroi in image_rois_left:
            if(iroi[0] <= rpoi[0] <= iroi[2] and iroi[1] <= rpoi[1] <= iroi[3]):
                match_left += 1
    for rpoi in radar_pois_right:
        for iroi in image_rois_right:
            if(iroi[0] <= rpoi[0] <= iroi[2] and iroi[1] <= rpoi[1] <= iroi[3]):
                match_right += 1
    # print detection results
    if args.information:
        print("\033[1;36mDetection Statistics:\033[0m")
        print("Radar Left: {},\tRadar Right: {}".format(radar_left, radar_right))
        print("Image Left: {},\tImage Right: {}".format(image_left, image_right))
        print("Match Left: {},\tMatch Right: {}".format(match_left, match_right))

    # publish the results
    msg_rad_cam = MsgRadCam()
    msg_rad_cam.radar_left   = radar_left
    msg_rad_cam.radar_right  = radar_right
    msg_rad_cam.camera_left  = image_left
    msg_rad_cam.camera_right = image_right
    msg_rad_cam.match_left   = match_left
    msg_rad_cam.match_right  = match_right
    msg_rad_cam.header.stamp = rospy.Time.now()
    pub.publish(msg_rad_cam)

    # save images
    if args.save:
        if args.trigger == 'match':
            if match_left != 0:
                radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            if match_right != 0:
                radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right, appendix='R')
        elif args.trigger == 'both':
            if radar_left != 0 and image_left != 0:
                radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            if radar_right != 0 and image_right != 0:
                radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right, appendix='R')
        elif args.trigger == 'either':
            if radar_left != 0 or image_left != 0:
                radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            if radar_right != 0 or image_right != 0:
                radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right, appendix='R')
        elif args.trigger == 'radar':
            if radar_left != 0:
                radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            if radar_right != 0:
                radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right,appendix='R')
        elif args.trigger == 'image':
            if image_left != 0:
                radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            if image_right != 0:
                radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right, appendix='R')
        else:
            radar2visual(OUTPUT_DIR, image2, radar_pois_left, image_rois_left, appendix='L')
            radar2visual(OUTPUT_DIR, image3, radar_pois_right, image_rois_right, appendix='R')
    
    frame_counter += 1


if __name__ == '__main__':
    # counter for debugging
    my_timer = 0
    frame_counter = 0

    # set command arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--off-yolo",
                        action      = 'store_true',
                        default     = False,
                        required    = False,
                        help        = "Disable yolo, save radar POIs and images per frame instead."
    )
    parser.add_argument("--fps",
                        type        = float,
                        default     = 2,
                        required    = False,
                        help        = "Approximate virtual fps."
                        )
    parser.add_argument("-i", "--information",
                        action      = 'store_true',
                        default     = False,
                        required    = False,
                        help        = "Print POIs, ROIs and statistics."
    )
    parser.add_argument("-s", "--save",
                        action      = 'store_true',
                        default     = False,
                        required    = False,
                        help        = "Save visualized POIs and ROIs as images."
    )
    parser.add_argument("-t", "--trigger",
                        choices     = ['match', 'both', 'either', 'radar', 'image', 'anyway'],
                        type        = str,
                        default     = 'match',
                        required    = False,
                        help        = "When to save images."
    )
    args = parser.parse_args()

    # get root path
    ROOT_DIR = Path(__file__).resolve().parents[2]
    # load config file
    CONFIG_DIR = ROOT_DIR.joinpath("config/config.yaml")
    with open(CONFIG_DIR, 'r') as f:
        try:
            config = yaml.load(f, Loader=yaml.FullLoader)
        except:
            print("\033[1;31mFailed to load config file.\033[0m")
            exit(1)
    OUTPUT_DIR = ROOT_DIR.joinpath(config['output']['RadCamFusion_dir'])
    MEASUREMENT_DIR = ROOT_DIR.joinpath(config['measurement']['measurement_dir'], 'measurement.txt')
    # load measurement file
    camera_index = {'camera11': 0, 'camera12': 1, 'camera13': 2, 'camera14': 3,
                    'camera2' : 4, 'camera3' : 5,
                    'camera41': 6, 'camera42': 7, 'camera43': 8, 'camera44': 9}
    measurement = np.loadtxt(MEASUREMENT_DIR)
    w2cs, c2ps = {}, {}
    for c in camera_index.keys():
        w2cs[c] = measurement[camera_index[c]][0:16].reshape(4, 4)
        c2ps[c] = measurement[camera_index[c]][16:28].reshape(3, 4)
    del measurement

    # initialize YOLO
    if not args.off_yolo:
        yolo = YOLO(ROOT_DIR)
        print("\033[0;32mYOLO initialized successfully.\033[0m")
    else:
        yolo = None
        print("\033[0;33mRunning in off-YOLO mode.\033[0m")
        OUTPUT_DIR = OUTPUT_DIR.joinpath("off_yolo")
        OUTPUT_DIR.mkdir(exist_ok=True)
    
    # initialize publisher
    pub = rospy.Publisher("/radar_camera_fused", MsgRadCam, queue_size=10)
    # initialize ROS node
    rospy.init_node('radar_camera_fusion', anonymous=True)
    # subscribe messages
    msg_radar   = message_filters.Subscriber('/radar_msgs_combined', MsgRadar)
    msg_image_2 = message_filters.Subscriber('/image_raw_2', Image)
    msg_image_3 = message_filters.Subscriber('/image_raw_3', Image)
    # syncronize time stamps
    sync = message_filters.ApproximateTimeSynchronizer([msg_radar, msg_image_2, msg_image_3], 1, 1)

    sync.registerCallback(old_fusion)

    print("\033[0;32mRadar-camera Fusion Initialized Sucessfully.\033[0m")

    rospy.spin()
