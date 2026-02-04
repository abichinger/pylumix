import requests
import time
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import os
import logging

logger = logging.getLogger(__name__)

class LumixCamera:
    def __init__(self, host='192.168.54.1'):
        self.host = host
        self.base_url = f'http://{host}/cam.cgi'
        self.binary_base_url = f'http://{host}:50001/'
        # Default session ID and device info
        self.device_id = '4D454930-0100-1000-8001-020A0003BD13'
        self.device_name = 'pylumix'

    def _request(self, mode, **kwargs):
        params = {'mode': mode}
        params.update(kwargs)
        try:
            response = requests.get(self.base_url, params=params, timeout=5)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            # We wrap the error but continue to allow the caller to handle it or it bubbles up
            raise RuntimeError(f"Request failed: {e}")

    def _parse_xml(self, content):
        try:
            return ET.fromstring(content)
        except ET.ParseError as e:
            raise RuntimeError(f"Failed to parse XML response: {e}, content: {content}")

    def req_acc(self):
        """Request access / pairing."""
        try:
            resp = self._request('accctrl', type='req_acc', value=self.device_id, value2=self.device_name)
            if resp.status_code == 200:
                return True
            xml = self._parse_xml(resp.text)
            # Check result
            result = xml.find('result')
            if result is not None and result.text == 'ok':
                return True
            else:
                print(f"Auth failed. Response: {resp.text}")
        except Exception as e:
            print(f"Auth exception: {e}")
        return False

    def get_state(self):
        """Get camera state (heartbeat)."""
        resp = self._request('getstate')
        return self._parse_xml(resp.text)

    def cam_cmd(self, value, value2=None):
        """Send a general camera command."""
        kwargs = {'value': value}
        if value2:
            kwargs['value2'] = value2
        resp = self._request('camcmd', **kwargs)
        return self._parse_xml(resp.text)

    def capture(self):
        """Trigger capture."""
        # Ensure we are in recording mode
        self.cam_cmd('recmode')
        return self.cam_cmd('capture')

    def video_recstart(self):
        self.cam_cmd('recmode')
        return self.cam_cmd('video_recstart')
    
    def video_recstop(self):
        return self.cam_cmd('video_recstop')

    def get_setting(self, setting_type):
        """Get a specific setting."""
        resp = self._request('getsetting', type=setting_type)
        return self._parse_xml(resp.text)

    def set_setting(self, setting_type, value):
        """Set a specific setting."""
        resp = self._request('setsetting', type=setting_type, value=value)
        return self._parse_xml(resp.text)

    def start_stream(self, port):
        """Start streaming to the specified UDP port."""
        # Switch to rec mode first
        self.cam_cmd('recmode')
        resp = self._request('startstream', value=port)
        return self._parse_xml(resp.text)

    def stop_stream(self):
        resp = self._request('stopstream')
        return self._parse_xml(resp.text)

    def get_content_info(self):
        self.cam_cmd('playmode')
        # Wait a bit for the mode switch
        time.sleep(1.0)
        resp = self._request('get_content_info')
        return self._parse_xml(resp.text)

    def download_file(self, filename, local_filename=None):
        """Download a file from the camera."""
        # Filename should be like /DL1000001.JPG
        # Ensure generic path construction if only ID provided? 
        # For now assume full path from camera listing or constructed by user.
        
        url = urljoin(self.binary_base_url, filename.lstrip('/')) # lstrip to ensure relative to base
        if not local_filename:
            local_filename = os.path.basename(filename)
            
        try:
            with requests.get(url, stream=True, timeout=10) as r:
                r.raise_for_status()
                with open(local_filename, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return local_filename
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            return None
