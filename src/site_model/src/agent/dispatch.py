# !/usr/bin/python3

import argparse
from pathlib import Path
from typing import Tuple
import numpy as np
import yaml

import rospy
import message_filters
from std_msgs.msg import Float64, Float64MultiArray
from nav_msgs.msg import Odometry
from ackermann_msgs.msg import AckermannDriveStamped
from msgs.msg._MsgRadCam import MsgRadCam  # radar camera fusion message type
from msgs.msg._MsgLidCam import MsgLidCam  # lidar camera fusion message type
from tf.transformations import euler_from_quaternion
from ..utils.visualization import rt_vis

from .agent import Agents
from .scene import SceneMap


class PublisherBundle:

    def __init__(self, vehicle_name: str) -> None:
        # l: left, r: right, f: front, r: rear
        # yapf: disable
        self.lr_wheel = rospy.Publisher('/{}/left_rear_wheel_velocity_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        self.rr_wheel = rospy.Publisher('/{}/right_rear_wheel_velocity_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        self.lf_wheel = rospy.Publisher('/{}/left_front_wheel_velocity_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        self.rf_wheel = rospy.Publisher('/{}/right_front_wheel_velocity_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        self.l_steering_hinge = rospy.Publisher('/{}/left_steering_hinge_position_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        self.r_steering_hinge = rospy.Publisher('/{}/right_steering_hinge_position_controller/command'.format(vehicle_name), Float64, queue_size=1)  # noqa: E501
        # yapf: enable

    def publish(self, throttle: float, steer: float) -> None:
        self.lr_wheel.publish(throttle)
        self.rr_wheel.publish(throttle)
        self.lf_wheel.publish(throttle)
        self.rf_wheel.publish(throttle)
        self.l_steering_hinge.publish(steer)
        self.r_steering_hinge.publish(steer)


def odom2pose(odom: Odometry) -> Tuple[np.ndarray, float]:
    pos = odom.pose.pose.position
    orient = odom.pose.pose.orientation
    r, p, y = euler_from_quaternion([orient.x, orient.y, orient.z, orient.w])
    return np.array([pos.x, pos.y]), y


def set_control(odom1: Odometry,
                odom2: Odometry,
                odom3: Odometry,
                odom4: Odometry,
                msgradcam: MsgRadCam = None,
                msglidcam: MsgLidCam = None) -> None:
    global pub_nums, pub_velocity
    global pub_1, pub_2, pub_3, pub_4

    poses = [odom2pose(odom1), odom2pose(odom2), odom2pose(odom3), odom2pose(odom4)]
    steers, throttles, nums_area = agents.navigate(poses, msgradcam, msglidcam)
    throttles = [t * 15 for t in throttles]

    pub_1.publish(throttles[0], steers[0])
    pub_2.publish(throttles[1], steers[1])
    pub_3.publish(throttles[2], steers[2])
    pub_4.publish(throttles[3], steers[3])

    nums = Float64MultiArray()
    velocity = Float64MultiArray()
    nums.data = nums_area
    velocity.data = [abs(t) for t in throttles]
    pub_nums.publish(nums)
    pub_velocity.publish(velocity)


def servo_commands() -> None:

    rospy.init_node('servo_commands', anonymous=True)

    # rospy.Subscriber("/ackermann_cmd_mux/output", AckermannDriveStamped, set_throttle_steer)

    sub_msgradcam = message_filters.Subscriber('/radar_camera_fused', MsgRadCam)
    sub_msglidcam = message_filters.Subscriber('/lidar_camera_fused', MsgLidCam)
    sub_key = message_filters.Subscriber('/ackermann_cmd_mux/output', AckermannDriveStamped)
    sub_odom1 = message_filters.Subscriber('/deepracer1/base_pose_ground_truth', Odometry)
    sub_odom2 = message_filters.Subscriber('/deepracer2/base_pose_ground_truth', Odometry)
    sub_odom3 = message_filters.Subscriber('/deepracer3/base_pose_ground_truth', Odometry)
    sub_odom4 = message_filters.Subscriber('/deepracer4/base_pose_ground_truth', Odometry)
    sync = message_filters.ApproximateTimeSynchronizer([sub_odom1, sub_odom2, sub_odom3, sub_odom4], 1, 1)
    sync.registerCallback(set_control)

    # spin() simply keeps python from exiting until this node is stopped
    rospy.spin()


if __name__ == '__main__':
    ROOT_DIR = Path(__file__).resolve().parents[2]
    CONFIG_FILE = ROOT_DIR.joinpath('config/config.yaml')
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", help="path to config file", metavar="FILE", required=False, default=str(CONFIG_FILE))
    parser.add_argument("--vis", help="whether to visualize", action='store_true', required=False)
    params = parser.parse_args()
    with open(params.config, 'r') as f:
        config = yaml.load(f, Loader=yaml.FullLoader)

    MAP_DIR = ROOT_DIR.joinpath(config['dispatch']['scene_map'])
    scene_map = SceneMap(MAP_DIR)
    agents = Agents(scene_map, 4)

    pub_nums = rospy.Publisher('/nums', Float64MultiArray, queue_size=1)
    pub_velocity = rospy.Publisher('/velocity', Float64MultiArray, queue_size=1)
    pub_1 = PublisherBundle('deepracer1')
    pub_2 = PublisherBundle('deepracer2')
    pub_3 = PublisherBundle('deepracer3')
    pub_4 = PublisherBundle('deepracer4')

    servo_commands()
