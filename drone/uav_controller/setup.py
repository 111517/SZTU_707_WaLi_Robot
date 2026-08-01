from setuptools import find_packages, setup

package_name = 'uav_controller'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/uav_controller.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='luhh',
    maintainer_email='luhh@todo.todo',
    description='UAV controller with T265 relay and battery relay',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'uav_controller_node = uav_controller.uav_controller_node:main',
            'vision_pose_relay = uav_controller.vision_pose_relay:main',
            'battery_relay = uav_controller.battery_relay:main',
        ],
    },
)
