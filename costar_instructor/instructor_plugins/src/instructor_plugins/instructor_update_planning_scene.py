#!/usr/bin/env python
import roslib; roslib.load_manifest('instructor_plugins')
import rospy 
from std_msgs.msg import *
from threading import Thread
# Qt
from PyQt4 import QtGui, QtCore, uic
from PyQt4.QtGui import *
from PyQt4.QtCore import *
# Beetree and Instructor
from service_node import ServiceNode
from instructor_core import NodeGUI
from instructor_core.instructor_qt import NamedField, NoteField, ColorOptions
import rospkg
from instructor_core.srv import *
import tf; 
import tf_conversions as tf_c
# Driver services for ur5
#from robotiq_c_model_control.srv import *
from std_srvs.srv import Empty

colors = ColorOptions().colors
# Node Wrappers -----------------------------------------------------------
class NodeActionUpdatePlanningSceneGUI(NodeGUI):
    def __init__(self):
        super(NodeActionUpdatePlanningSceneGUI,self).__init__(color='purple')
        self.title.setText('UPDATE PLANNING SCENE')
        self.title.setStyleSheet('background-color:'+colors['purple'].normal+';color:#ffffff')
        self.wait_finish = NamedField('Wait', '','purple')
        self.wait_finish.set_field('1')
        self.note = NoteField('(1 = true, 0 = false)','purple')
        self.layout_.addWidget(self.wait_finish)
        self.layout_.addWidget(self.note)

    def save_data(self,data):
        return data
    def load_data(self,data):
        pass
    def generate(self):
        if all([self.name.full(),self.wait_finish.full()]):
            return NodeActionUpdatePlanningScene(self.get_name(),self.get_label(),int(self.wait_finish.get()))
        else:
            rospy.logerr('check that all menu items are properly selected for this node')
            return 'ERROR: check that all menu items are properly selected for this node'

# Nodes -------------------------------------------------------------------
class NodeActionUpdatePlanningScene(ServiceNode):
    def __init__(self,name,label,wait_finish):
        L = 'UPDATE PLANNING SCENE'
        super(NodeActionUpdatePlanningScene,self).__init__(name,L,colors['purple'].normal,"MoveIt Planning Scene")
        # Reset params
        self.planning_scene_service_thread = Thread(target=self.make_service_call, args=('',1))
        if wait_finish == 0:
            self.wait_finish = False
        else:
            self.wait_finish = True

    def make_service_call(self,request,*args):
        # Check to see if service exists
        service_name = '/planningSceneGenerator/planningSceneGenerator'
        try:
            rospy.wait_for_service(service_name)
        except rospy.ROSException as e:
            rospy.logerr('Could not find planning scene generation service')
            self.finished_with_success = False
            return
        # Make servo call to set pose
        try:
            planning_scene_open_proxy = rospy.ServiceProxy(service_name,Empty)
            # Send Open Command
            rospy.loginfo('MoveIt Planning Scene Server '+self.get_node_type()+' Started')
            result = planning_scene_open_proxy()
            self.finished_with_success = True
            return

        except (rospy.ServiceException), e:
            rospy.logerr('There was a problem with the service:')
            rospy.logerr(e)
            self.finished_with_success = False
            return
