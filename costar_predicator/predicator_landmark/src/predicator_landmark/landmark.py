import rospy

from predicator_msgs.msg import *
from predicator_msgs.srv import *

import tf
import tf_conversions.posemath as pm
import numpy as np

from costar_objrec_msgs.msg import *

'''
convert detected objects into predicate messages we can query later on
'''
class GetWaypointsService:

    valid_msg = None

    def __init__(self,world="world",service=True,ns=""):
        #self.pub = rospy.Publisher('/predicator/input', PredicateList, queue_size=1000)
        #self.vpub = rospy.Publisher('/predicator/valid_input', ValidPredicates, queue_size=1000)
        #self.valid_msg = ValidPredicates()
        #self.valid_msg.pheader.source = rospy.get_name()
        #self.valid_msg.predicates.append('class_detected')
        #self.valid_msg.predicates.append('member_detected')

        #self.sub = rospy.Subscriber('/landmark_definitions', LandmarkDefinition, self.callback)
        self.world = world
        self.and_srv = rospy.ServiceProxy('/predicator/match_AND',Query)
        if service:
            self.service = rospy.Service('/predicator/get_waypoints',GetWaypoints,self.get_waypoints_srv)
        self.listener = tf.TransformListener()

        self.detected_objects = rospy.Subscriber(ns + '/detected_object_list',
                                                 DetectedObjectList,
                                                 self.detected_objects_cb)
        self.obj_symmetries = {}


    def detected_objects_cb(self,msg):
        for obj in msg.objects:
            obj.symmetry.z_symmetries = max(1,obj.symmetry.z_symmetries)
            obj.symmetry.y_symmetries = max(1,obj.symmetry.y_symmetries)
            obj.symmetry.x_symmetries = max(1,obj.symmetry.x_symmetries)
            self.obj_symmetries[obj.object_class] = obj.symmetry
        
    def get_waypoints_srv(self,req):
        resp = GetWaypointsResponse()
        (poses, names) = self.get_waypoints(req.frame_type,req.predicates,req.transforms,req.names)

        if poses is None or len(poses) < 1:
            resp.msg = 'FAILURE -- message not found!'
            resp.success = False
        else:
            resp.waypoints.poses = poses
            resp.names = names
            resp.msg = 'SUCCESS -- done!'
            resp.success = True

        return resp

    def get_waypoints(self, frame_type, predicates, transforms, names, constraints):
        '''
        Parameters:
        -----------
        frame_type: object class to match when generating new frames
        predicates: other list of predicates to add
        transforms: used to generate the actual poses
        names: should be same size as transforms
        above: prunes list of transforms based on criteria, transforms should
               be above their parent frame in the world coordinates
        '''
        self.and_srv.wait_for_service()

        if not len(names) == len(transforms):
            raise RuntimeError('Names and transforms provided to landmark get_waypoints must be the same length')
        if not len(names) == 1:
            raise NotImplementedError('Passing a list of multiple transforms to get_waypoints is not yet supported.') 

        type_predicate = PredicateStatement()
        type_predicate.predicate = frame_type
        type_predicate.params = ['*','','']

        print "----"
        print "predicate(s) to match:"
        print predicates
        print "----"
        print "type predicate to match:"
        print type_predicate

        res = self.and_srv([type_predicate]+predicates)

        if len(res.matching) == 0:
            rospy.logerr("Failed to find any matching objects!")
            return None
        else:
            rospy.loginfo("Predicator found matches: " + str(res.matching))
        #print res

        if (not res.found) or len(res.matching) < 1:
          return None

        poses = []
        for tform in transforms:
            poses.append(pm.fromMsg(tform))
            break # we only do one

        if frame_type not in self.obj_symmetries.keys():
            self.obj_symmetries[frame_type] = ObjectSymmetry()
            self.obj_symmetries[frame_type].z_symmetries = 1
            self.obj_symmetries[frame_type].y_symmetries = 1
            self.obj_symmetries[frame_type].x_symmetries = 1

        # Get only unique rotation matrices from the list of rotation matrices generated from RPY
        quaternion_list = list()
        for i in xrange(0, self.obj_symmetries[frame_type].z_symmetries):
            for j in xrange(0, self.obj_symmetries[frame_type].y_symmetries):
                for k in xrange(0, self.obj_symmetries[frame_type].x_symmetries):
                    theta_z = i * self.obj_symmetries[frame_type].z_rotation
                    theta_y = j * self.obj_symmetries[frame_type].y_rotation
                    theta_x = k * self.obj_symmetries[frame_type].x_rotation
                    rot_matrix = pm.Rotation.RPY(theta_x,theta_y,theta_z)
                    quaternion_list.append(rot_matrix.GetQuaternion())
        quaternion_list = np.array(quaternion_list)
        
        unique_brute_force = list()
        for i in xrange(len(quaternion_list)):
            unique = True
            for j in xrange(i, len(quaternion_list)):
                if i == j:
                    continue
                else:
                    if abs(quaternion_list[i].dot(quaternion_list[j])) > 0.99:
                        unique = False
                        break
            if unique:
                unique_brute_force.append(i)

        unique_rot_matrix = list()
        for index in unique_brute_force:
            unique_rot_matrix.append(  pm.Rotation.Quaternion( *quaternion_list[index].tolist() )  )

        new_poses = []
        new_names = []
        objects = []

        for match in res.matching:
            try:
                (trans,rot) = self.listener.lookupTransform(self.world, match, rospy.Time(0))
                match_tform = pm.fromTf((trans,rot))
                rospy.loginfo("Checking " + str(match) + " from " + str(self.world))

                if frame_type in self.obj_symmetries:
                    for rot_matrix in unique_rot_matrix:
                        tform = pm.Frame(rot_matrix)
                        world_tform = match_tform * tform * poses[0]
                        violated = False

                        for constraint in constraints:
                            v1 = match_tform.p[constraint.pose_variable]
                            v2 = world_tform.p[constraint.pose_variable]
                            if constraint.greater and not (v2 >= v1 + constraint.threshold):
                                violated = True
                                #print "VIOLATED", constraint
                                rospy.logwarn("constraint violation: " + str(v2)  + "<" + str(v1))
                                break
                            elif not constraint.greater and not (v2 <= v1 - constraint.threshold):
                                violated = True
                                rospy.logwarn("constraint violation: " + str(v2)  + ">" + str(v1))
                                #print "VIOLATED", constraint
                                break
                        if violated:
                            continue
                        #else:
                        #    print match_tform.p, world_tform.p

                        new_poses.append(pm.toMsg(world_tform))
                        new_names.append(match + "/" + names[0] + "/x%fy%fz%f"%(rot_matrix.GetRPY()))

                        objects.append(match)

            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                rospy.logwarn('Could not find transform from %s to %s!'%(self.world,match))

        return (new_poses, new_names, objects)
        
