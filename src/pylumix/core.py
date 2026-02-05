import requests
import time
import socket
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
import os
import logging

logger = logging.getLogger(__name__)


class LumixCamera:
    def __init__(self, host="192.168.54.1"):
        self.host = host
        self.base_url = f"http://{host}/cam.cgi"
        self.binary_base_url = f"http://{host}:50001/"
        self.soap_url = f"http://{host}:60606/Server0/CDS_control"
        # Default session ID and device info
        self.device_id = "4D454930-0100-1000-8001-020A0003BD13"
        self.device_name = "pylumix"

    def _request(self, mode, **kwargs):
        params = {"mode": mode}
        params.update(kwargs)
        response = requests.get(self.base_url, params=params, timeout=5)
        response.raise_for_status()
        return response

    def cam_cmd(self, value, value2=None):
        """Send a general camera command."""
        kwargs = {"value": value}
        if value2:
            kwargs["value2"] = value2
        resp = self._request("camcmd", **kwargs)
        return self._parse_xml(resp.text)

    def _parse_xml(self, content):
        try:
            return ET.fromstring(content)
        except ET.ParseError as e:
            raise RuntimeError(f"Failed to parse XML response: {e}, content: {content}")

    def req_acc(self) -> bool:
        """Request access / pairing."""
        resp = self._request(
            "accctrl", type="req_acc", value=self.device_id, value2=self.device_name
        )
        if resp.status_code != 200:
            logger.warning(f"Auth failed. Response: {resp.text}")
            return False
        return True

    def ensure_access(self):
        # Check for access rejection and try to request access
        state = self.get_state()
        # The XML root is usually <camrply>, so we look for 'result' direct child
        result = state.find("result")

        if result is not None and (result.text or "").strip() == "ok":
            return True

        if self.req_acc():
            return True

        raise RuntimeError("Access request failed. Check connection.")

    def get_state(self):
        """Get camera state (heartbeat)."""
        resp = self._request("getstate")
        return self._parse_xml(resp.text)
    
    def sd_access(self) -> bool:
        state = self.get_state()
        node = state.find(".//sd_access")
        return node is not None and (node.text or "") == 'on'

    def capture(self, timeout: float = 10.0, poll_interval: float = 0.2) -> bool:
        """Trigger capture and wait until total_content_number increases by one.
        Polls every poll_interval seconds (default 0.3s) up to timeout seconds.
        Returns True on success, raises RuntimeError on failure/timeout.
        """
        self.cam_cmd("recmode")

        # Trigger capture
        self.cam_cmd("capture")

        sd_used = False
        end_time = time.time() + timeout
        while time.time() < end_time:
            sd_access = self.sd_access()
            if not sd_access and sd_used:
                return True
            sd_used = sd_used or sd_access
            time.sleep(poll_interval)

        # return False
        raise RuntimeError("Timeout waiting for image")

    def video_recstart(self):
        self.cam_cmd("recmode")
        return self.cam_cmd("video_recstart")

    def video_recstop(self):
        return self.cam_cmd("video_recstop")

    def get_setting(self, setting_type):
        """Get a specific setting."""
        resp = self._request("getsetting", type=setting_type)
        return self._parse_xml(resp.text)

    def set_setting(self, setting_type, value):
        """Set a specific setting."""
        resp = self._request("setsetting", type=setting_type, value=value)
        return self._parse_xml(resp.text)

    def start_stream(self, port):
        """Start streaming to the specified UDP port."""
        # Switch to rec mode first
        self.cam_cmd("recmode")
        resp = self._request("startstream", value=port)
        return self._parse_xml(resp.text)

    def stop_stream(self):
        resp = self._request("stopstream")
        return self._parse_xml(resp.text)

    def stream_preview(self, port=49152):
        """Generator that yields UDP packets from the preview stream."""
        self.cam_cmd("recmode")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(('0.0.0.0', port))
        except OSError as e:
            raise RuntimeError(f"Error binding to port {port}: {e}")

        sock.settimeout(2.0)

        try:
            self.start_stream(port)
            while True:
                try:
                    data, _ = sock.recvfrom(65536)
                    yield data
                except socket.timeout:
                    # Send heartbeat to keep stream alive
                    self.get_state()
        finally:
            try:
                self.stop_stream()
            except Exception:
                pass
            sock.close()

    def get_preview_image(self, port=49152):
        """Capture a single JPEG frame from the preview stream."""
        for data in self.stream_preview(port):
            # Simple check for JPEG in this packet (SOI ... EOI)
            start = data.find(b'\xff\xd8')
            end = data.find(b'\xff\xd9')

            if start != -1 and end != -1 and end > start:
                return data[start : end + 2]
        return None

    def get_content_info(self):
        self.cam_cmd("playmode")
        # Wait a bit for the mode switch
        time.sleep(1.0)
        resp = self._request("get_content_info")
        return self._parse_xml(resp.text)
    

    def total_content_number(self) -> int:
        root = self.get_content_info()
        node = root.find("total_content_number")
        if node is None or (node.text or "").strip() == "":
            raise RuntimeError("total_content_number not found in response")
        try:
            return int(node.text.strip())
        except ValueError:
            raise RuntimeError(f"Invalid total_content_number value: {node.text!r}")

    def download_file(self, filename, local_filename=None): 
        """Download a file from the camera."""
        # Filename should be like /DL1000001.JPG
        # Ensure generic path construction if only ID provided?
        # For now assume full path from camera listing or constructed by user.

        url = urljoin(
            self.binary_base_url, filename.lstrip("/")
        )  # lstrip to ensure relative to base
        if not local_filename:
            local_filename = os.path.basename(filename)

        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                with open(local_filename, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        f.write(chunk)
            return local_filename
        except Exception as e:
            print(f"Failed to download {url}: {e}")
            return None

    def get_latest_item(self):
        """Get the most recently added item info."""
        try:
            # We need total count to find the index of the last item
            total = self.total_content_number()
            if total > 0:
                # Browse requesting 1 item at proper index (0-based)
                # Assumes content is appended at the end
                items = self.browse(start_index=total - 1, count=1)
                if items:
                    return items[0]
        except Exception as e:
            logger.error(f"Failed to get latest item: {e}")
        return None

    def download_to_memory(self, filename):
        """Download a file into memory."""
        url = urljoin(self.binary_base_url, filename.lstrip("/"))
        try:
            with requests.get(url, timeout=30) as r:
                r.raise_for_status()
                return r.content
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            return None

    def browse(self, object_id="0", start_index=0, count=15):
        """Browse content using UPnP ContentDirectory service."""
        self.cam_cmd("playmode")
        time.sleep(1)

        soap_action = '"urn:schemas-upnp-org:service:ContentDirectory:1#Browse"'
        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": soap_action,
            "User-Agent": "Panasonic Android/1 DM-CP",
        }

        body = f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
 <s:Body>
  <u:Browse xmlns:u="urn:schemas-upnp-org:service:ContentDirectory:1" xmlns:pana="urn:schemas-panasonic-com:pana">
   <ObjectID>{object_id}</ObjectID>
   <BrowseFlag>BrowseDirectChildren</BrowseFlag>
   <Filter>*</Filter>
   <StartingIndex>{start_index}</StartingIndex>
   <RequestedCount>{count}</RequestedCount>
   <SortCriteria></SortCriteria>
   <pana:X_FromCP>LumixLink2.0</pana:X_FromCP>
  </u:Browse>
 </s:Body>
</s:Envelope>"""

        try:
            resp = requests.post(self.soap_url, data=body, headers=headers, timeout=30)
            resp.raise_for_status()

            root = ET.fromstring(resp.text)

            # Helper to find Result recursively regardless of namespace
            result_node = None
            for elem in root.iter():
                if "Result" in elem.tag:
                    result_node = elem
                    break

            items_list = []
            if result_node is not None and result_node.text:
                didl_xml = result_node.text
                didl_root = ET.fromstring(didl_xml)

                for item in didl_root.iter():
                    if "item" in item.tag:
                        # Extract URL from res
                        res_url = None
                        for child in item:
                            if "res" in child.tag:
                                res_url = child.text
                                break

                        # Extract title
                        title = None
                        for child in item:
                            if "title" in child.tag:
                                title = child.text
                                break

                        items_list.append(
                            {"id": item.get("id"), "title": title, "url": res_url}
                        )
            return items_list

        except Exception as e:
            print(f"Browse failed: {e}")
            return []
