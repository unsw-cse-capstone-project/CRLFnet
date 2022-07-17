#############################################################
#   This py file acts as agent representing the overpass.   #
#############################################################

from pathlib import Path
import argparse
import yaml
import rospy
from termcolor import colored

import message_filters
from msgs.msg._MsgRadCam import *   # radar camera fusion message type
from msgs.msg._MsgLidCam import *   # lidar camera fusion message type


def main(msgradcam: MsgRadCam, msglidcam: MsgLidCam):
    AREA_CIRCLE = 1.92 * 2 * 2.92
    AREA_INTERSECTION = 1.92 * 2 * 2.5
    AREA_OVERPASS = 0
    # caculate the density of vehicles
    density_overpass = None / AREA_OVERPASS
    density_circle = msglidcam.num_circle / AREA_CIRCLE
    density_intersection = msglidcam.num_intersection / AREA_INTERSECTION


if __name__ == '__main__':
    # get ROOT DIR
    ROOT_DIR = Path(__file__).resolve().parents[2]
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--config",
                        help="path to config file",
                        metavar="FILE",
                        required=False,
                        default= str(ROOT_DIR.joinpath("config/config.yaml"))
                        )
    params = parser.parse_args()

    with open(params.config, 'r') as f:
        try:
            config = yaml.load(f, Loader=yaml.FullLoader)
        except:
            print(colored('Config file could not be read.','red'))
            exit(1)

    rospy.init_node('agent_one', anonymous=True)

    sub_msgradcam = message_filters.Subscriber('/radar_camera_fused', MsgRadCam)
    sub_msglidcam = message_filters.Subscriber('/lidar_camera_fused', MsgLidCam)
 
    sync = message_filters.ApproximateTimeSynchronizer([sub_msgradcam, sub_msglidcam], 1, 1)    # syncronize time stamps
    sync.registerCallback(main)
    print("Agent Set.")
    rospy.spin()