#!/bin/bash

echo "Setting up system dependencies and FastAPI app..."

# Install Python and Git
if grep -qi "ubuntu" /etc/*release; then
  apt update -qq
  apt install -y python3 python3-venv python3-pip git
elif grep -qi "centos" /etc/*release; then
  yum install -y python3 python3-pip git
else
  echo "Unsupported OS"
  exit 1
fi

# Clone project
cd /var/www || exit
rm -rf ngo-system
git clone https://github.com/Ivo2022/fastapi.git ngo-system
cd ngo-system

# Setup virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Deployment complete. Now enable the systemd service to run your app."
