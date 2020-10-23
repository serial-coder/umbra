#!/bin/bash 

echo "###################################"
echo "Installing Requirements (Python 3.7)"
echo "###################################"

sudo apt update &&
    sudo apt install -y software-properties-common &&
    sudo add-apt-repository -y ppa:deadsnakes/ppa &&
    sudo apt install -y python3.7 python3.7-dev python3-dev python3-pip ansible git aptitude cpanminus

sudo pip3 install setuptools

# used by report generator to parse DOT file to ascii art
sudo cpanm Graph::Easy

echo "###################################"
echo "Installing Umbra"
echo "###################################"

cd ../
sudo python3.7 setup.py develop
cd -

echo "###################################"
echo "Installing mininet"
echo "###################################"

sudo apt install mininet

echo "###################################"
echo "Installing Containernet"
echo "###################################"

sudo python3.7 -m pip install -U cffi pexpect

git clone https://github.com/banoris/containernet
cd containernet/ansible
sudo ansible-playbook -i "localhost," -c local install.yml
cd ..
sudo python3.7 setup.py install
cd ..

echo "##################################################"
echo "Setup dockprom v3.17.1 for UI monitoring dashboard"
echo "##################################################"

git clone -b v3.17.1 https://github.com/stefanprodan/dockprom.git

sudo usermod -aG docker $USER
