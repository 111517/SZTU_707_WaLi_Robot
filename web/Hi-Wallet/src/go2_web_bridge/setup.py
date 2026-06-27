from setuptools import find_packages, setup
from glob import glob

package_name = 'go2_web_bridge'

setup(
    name=package_name,
    version='1.0.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Go2 Web Dashboard',
    maintainer_email='user@example.com',
    description='Minimal bridge + launch for Go2 web dashboard',
    license='BSD',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'unitree_bridge_node = go2_web_bridge.unitree_bridge_node:main',
        ],
    },
)
