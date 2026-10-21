# SPDX-FileCopyrightText: 2026
# SPDX-License-Identifier: MIT
"""Forward kinematics and bounded IK from the exact official URDF joint origins."""
import xml.etree.ElementTree as ET
import numpy as np
from scipy.spatial.transform import Rotation
from scipy.optimize import least_squares

class Robot:
    def __init__(self,path,base=(.58,-.48,-.60),yaw=np.pi/2):
        self.xml=ET.parse(path).getroot();self.joints=self.xml.findall('joint')
        self.base=np.eye(4);self.base[:3,:3]=Rotation.from_euler('z',yaw).as_matrix();self.base[:3,3]=base
        self.arm=[j for j in self.joints if j.attrib['name'].startswith('right_') and '_hand_' not in j.attrib['name']]
        self.names=[j.attrib['name'] for j in self.arm]
        self.lo=np.array([float(j.find('limit').attrib['lower']) for j in self.arm]);self.hi=np.array([float(j.find('limit').attrib['upper']) for j in self.arm])
        self.offset=np.array([.13,.065,0.])
        self.fixed={'LZ_mt_Joint':0,'LZ_it_Joint':0,'left_elbow_joint':1.1,'left_shoulder_roll_joint':.15}
    def fk(self,q):
        vals={**self.fixed,**q};out={'AGV_link':self.base.copy()};todo=list(self.joints)
        while todo:
            before=len(todo)
            for j in todo[:]:
                parent=j.find('parent').attrib['link']
                if parent not in out:continue
                o=j.find('origin');tr=np.eye(4)
                if o is not None:
                    tr[:3,3]=np.fromstring(o.attrib.get('xyz','0 0 0'),sep=' ')
                    tr[:3,:3]=Rotation.from_euler('xyz',np.fromstring(o.attrib.get('rpy','0 0 0'),sep=' ')).as_matrix()
                move=np.eye(4);angle=vals.get(j.attrib['name'],0)
                if j.attrib['type']!='fixed':
                    axis=np.fromstring(j.find('axis').attrib.get('xyz','1 0 0'),sep=' ')
                    if j.attrib['type']=='prismatic':move[:3,3]=axis*angle
                    else:move[:3,:3]=Rotation.from_rotvec(axis*angle).as_matrix()
                out[j.find('child').attrib['link']]=out[parent]@tr@move;todo.remove(j)
            assert len(todo)<before,'URDF graph disconnected'
        return out
    def ik(self,xyz,previous=None):
        desired=np.array([[0,0,1],[0,1,0],[-1,0,0.]])
        offset=self.offset
        def residual(q):
            t=self.fk(dict(zip(self.names,q)))['right_hand_palm_link'];pos=t[:3,3]+t[:3,:3]@offset
            return np.r_[(pos-xyz)*8,Rotation.from_matrix(desired@t[:3,:3].T).as_rotvec()*.55]
        seed=np.array([-.4,-.3,0,1.4,0,0,0]) if previous is None else previous
        result=least_squares(residual,np.clip(seed,self.lo+.001,self.hi-.001),bounds=(self.lo,self.hi),max_nfev=140,xtol=1e-8,ftol=1e-8,gtol=1e-8)
        return result.x,float(np.linalg.norm(residual(result.x)[:3])/8)
