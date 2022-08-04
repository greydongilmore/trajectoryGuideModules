#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul  2 21:52:23 2021

@author: greydon
"""
import os
import numpy as np
from matplotlib import pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.patches import FancyArrowPatch
from mpl_toolkits.mplot3d import proj3d


class Arrow3D(FancyArrowPatch):
	def __init__(self, xs, ys, zs, *args, **kwargs):
		FancyArrowPatch.__init__(self, (0,0), (0,0), *args, **kwargs)
		self._verts3d = xs, ys, zs

	def draw(self, renderer):
		xs3d, ys3d, zs3d = self._verts3d
		xs, ys, zs = proj3d.proj_transform(xs3d, ys3d, zs3d, renderer.M)
		self.set_positions((xs[0],ys[0]),(xs[1],ys[1]))
		FancyArrowPatch.draw(self, renderer)

def Rx(phi):
	return np.array([[1, 0, 0],
					 [0, np.cos(phi), -np.sin(phi)],
					 [0, np.sin(phi), np.cos(phi)]])

def Ry(theta):
	return np.array([[np.cos(theta), 0, np.sin(theta)],
					 [0, 1, 0],
					 [-np.sin(theta), 0, np.cos(theta)]])

def Rz(psi):
	return np.array([[np.cos(psi), -np.sin(psi), 0],
					 [np.sin(psi), np.cos(psi), 0],
					 [0, 0, 1]])


out_path='/media/greydon/KINGSTON34/phdCandidacy/thesis/imgs'

arrow_prop_dict = dict(mutation_scale=20, arrowstyle='-|>', color='k', shrinkA=0, shrinkB=0)
text_options = {'horizontalalignment': 'center',
				'verticalalignment': 'center',
				'fontsize': 15,
				'fontweight': 'bold'}
max_val=1

#%%

# define origin
o = np.array([0,0,0])

# define ox0y0z0 axes
x0 = np.array([1,0,0])
y0 = np.array([0,1,0])
z0 = np.array([0,0,1])

# define ox1y1z1 axes
psi = 45 * np.pi / 180
x1 = Rz(psi).dot(x0)
y1 = Rz(psi).dot(y0)
z1 = Rz(psi).dot(z0)


# produce figure
fig = plt.figure(figsize=(14,6))
ax = fig.add_subplot(121, projection='3d')

# plot x,y,z axes
a=Arrow3D([o[0], x0[0]], [o[1], x0[1]], [o[2], x0[2]], **arrow_prop_dict)
ax.add_artist(a)
a=Arrow3D([o[0], y0[0]], [o[1], y0[1]], [o[2], y0[2]], **arrow_prop_dict)
ax.add_artist(a)
a=Arrow3D([o[0], z0[0]], [o[1], z0[1]], [o[2], z0[2]], **arrow_prop_dict)
ax.add_artist(a)
ax.set_xlim([o[0], max_val])
ax.set_ylim([o[0], max_val])
ax.set_zlim([o[0], max_val])

# plot ox1y1z1 axes
ax.plot(x1[0], y1[1], z1[2], markerfacecolor='k', markeredgecolor='k', marker='o', markersize=5)

ax.plot([x1[0], x1[0]], [y1[1], y1[1]], [o[0], z1[2]], 'k--', linewidth=1)
ax.plot([x1[0], x1[0]], [o[0], y1[1]], [o[0], o[0]], 'k--', linewidth=1)
ax.plot([o[0], x1[0]], [y1[1], y1[1]], [o[0], o[0]], 'k--', linewidth=1)

# add labels for x,y,z axes
ax.text(1.2*x0[0],1.2*x0[1],1.2*x0[2],r'$x$', **text_options)
ax.text(1.1*y0[0],1.1*y0[1],1.1*y0[2],r'$y$', **text_options)
ax.text(1.1*z0[0],1.1*z0[1],1.1*z0[2],r'$z$', **text_options)

# add label for origin
ax.text(0.0,0.0,-0.05,r'$o$', **text_options)

ax.text(x1[0]+.12,y1[1]/2, 0, r'$y$', **text_options)
ax.text(x1[0]/2,y1[1]+0.07, 0, r'$x$', **text_options)
ax.text(x1[0]+.05, y1[1]+.05, z0[2]/1.9, r'$z$', **text_options)

# add point label
ax.text(x0[0]-.03, y0[1]-.03, z0[2]+.05, r'$P(x,y,z)$', **text_options)

ax.set_title('Cartesian coordinate system', fontdict={'fontsize': 18, 'fontweight': 'bold'})

# show figure
ax.view_init(elev=10, azim=22)
ax.dist = 10
ax.set_axis_off()
ax.grid(True)
plt.draw()

#%%

plt.savefig(os.path.join(out_path,"cartesian_coordinates.svg"),transparent=True)
plt.savefig(os.path.join(out_path,"cartesian_coordinates.png"),dpi=300)
plt.close()

#%% https://stackoverflow.com/a/29188796

# define origin
o = np.array([0,0,0])

# define ox0y0z0 axes
x0 = np.array([1,0,0])
y0 = np.array([0,1,0])
z0 = np.array([0,0,1])

# define ox1y1z1 axes
psi = 45 * np.pi / 180
x1 = Rz(psi).dot(x0)
y1 = Rz(psi).dot(y0)
z1 = Rz(psi).dot(z0)

# define ox2y2z2 axes
theta = 45 * np.pi / 180
x2 = Rz(psi).dot(Ry(theta)).dot(x0)
y2 = Rz(psi).dot(Ry(theta)).dot(y0)
z2 = Rz(psi).dot(Ry(theta)).dot(z0)

phi = 45 * np.pi / 180
x3 = Rz(psi).dot(Ry(theta)).dot(Rx(phi)).dot(x0)
y3 = Rz(psi).dot(Ry(theta)).dot(Rx(phi)).dot(y0)
z3 = Rz(psi).dot(Ry(theta)).dot(Rx(phi)).dot(z0)

# produce figure
#fig = plt.figure(figsize=(10,10))
ax = fig.add_subplot(122, projection='3d')

# plot x,y,z axes
a=Arrow3D([o[0], x0[0]], [o[1], x0[1]], [o[2], x0[2]], **arrow_prop_dict)
ax.add_artist(a)
a=Arrow3D([o[0], y0[0]], [o[1], y0[1]], [o[2], y0[2]], **arrow_prop_dict)
ax.add_artist(a)
a=Arrow3D([o[0], z0[0]], [o[1], z0[1]], [o[2], z0[2]], **arrow_prop_dict)
ax.add_artist(a)
ax.set_xlim([o[0], max_val])
ax.set_ylim([o[0], max_val])
ax.set_zlim([o[0], max_val])

# plot ox1y1z1 axes
ax.plot([o[0], x1[0]], [o[1], y1[1]], [o[2], z1[2]], color='r', linewidth=1)
ax.plot(x1[0], y1[1], z1[2], markerfacecolor='k', markeredgecolor='k', marker='o', markersize=5)

ax.plot([x1[0], x1[0]], [y1[1], y1[1]], [o[0], z1[2]], 'k--', linewidth=1)
ax.plot([o[0], x1[0]], [o[0], y1[1]], [o[0], o[0]], 'k--', linewidth=1)

# mark z0 rotation angles (psi)
arc = np.linspace(0,psi)
p = np.array([np.cos(arc),np.sin(arc),arc * 0]) * 0.6
ax.plot(p[0,:],p[1,:],p[2,:],'k')

# mark y1 rotation angles (theta)
arc = np.linspace(0,theta)
p = np.array([np.sin(arc),arc * 0,np.cos(arc)]) * 0.6
p = Rz(psi).dot(p)
ax.plot(p[0,:],p[1,:],p[2,:],'k')

# add labels for x axes
ax.text(1.2*x0[0],1.2*x0[1],1.2*x0[2],r'$x$', **text_options)

# add lables for y axes
ax.text(1.1*y0[0],1.1*y0[1],1.1*y0[2],r'$y$', **text_options)

# add lables for z axes
ax.text(1.1*z0[0],1.1*z0[1],1.1*z0[2],r'$z$', **text_options)

# add label for origin
ax.text(0.0,0.0,-0.05,r'$o$', **text_options)

# add psi angle labels
m = 0.55 * ((x0 + x1) / 2.0)
ax.text(m[0], m[1], m[2]-.1, r'$\varphi$', **text_options)

# add theta angle lables
m = 0.9*((x1 - x2))
ax.text(m[0], m[1], m[2], r'$\theta$', **text_options)

# add r label
ax.text(x2[0]-.1, x2[1]-.1, x2[2]*-1, r'$r$', **text_options)

# add point label
ax.text(x0[0]-.05, y0[1]-.05, z0[2]+.05, r'$(r,\theta,\varphi)$', **text_options)

ax.set_title('Spherical coordinate system', fontdict={'fontsize': 18, 'fontweight': 'bold'})

# show figure
ax.view_init(elev=10, azim=22)
ax.dist = 10
ax.set_axis_off()
ax.grid(True)
plt.draw()


#%%

plt.savefig(os.path.join(out_path,"spherical_coordinates.svg"),transparent=True)
plt.savefig(os.path.join(out_path,"spherical_coordinates.png"),dpi=300)
plt.close()

#%%
plt.tight_layout()
plt.savefig(os.path.join(out_path,"coordinate_systems.svg"),transparent=True)
plt.savefig(os.path.join(out_path,"coordinate_systems.png"),transparent=True,dpi=300)
plt.close()
