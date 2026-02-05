import argparse
import sys
import socket
import logging
import signal
import xml.etree.ElementTree as ET
from .core import LumixCamera

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Control Panasonic Lumix Camera")
    parser.add_argument('--host', default='192.168.54.1', help='Camera IP address')
    parser.add_argument('--stdout', action='store_true', help='Output stream to stdout (for preview/video)')
    parser.add_argument('--out', help='Output file')
    
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Info
    subparsers.add_parser('info', help='Get camera info')
    
    # Preview
    subparsers.add_parser('preview', help='Start live preview stream')
    
    # Image
    img_parser = subparsers.add_parser('image', help='Capture image')
    img_parser.add_argument('--preview', action='store_true', help='Capture from preview stream instead of full capture')
    
    # Video
    vid_parser = subparsers.add_parser('video', help='Record video')
    vid_parser.add_argument('action', choices=['start', 'stop'], help='Start or stop recording')

    # Config
    cfg_parser = subparsers.add_parser('config', help='Get or set configuration')
    cfg_parser.add_argument('setting', help='Setting name (e.g., iso, aperture)')
    cfg_parser.add_argument('value', nargs='?', help='New value for setting')

    # Download
    dl_parser = subparsers.add_parser('download', help='Download a file')
    dl_parser.add_argument('file', help='File path on camera (e.g. /DL1000001.JPG)')
    dl_parser.add_argument('--dest', help='Destination filename')

    # Browse/List
    ls_parser = subparsers.add_parser('ls', help='List files on camera')
    ls_parser.add_argument('--start', type=int, default=0, help='Starting index')
    ls_parser.add_argument('--count', type=int, default=15, help='Number of items')

    args = parser.parse_args()
    
    camera = LumixCamera(host=args.host)
    camera.ensure_access()

    if args.command == 'info':
        try:
            state = camera.get_state()
            # Basic printing of XML content recursively
            def print_elem(elem, level=0):
                indent = "  " * level
                text = elem.text.strip() if elem.text else ""
                print(f"{indent}{elem.tag}: {text}")
                for child in elem:
                    print_elem(child, level + 1)
            print_elem(state)
        except Exception as e:
            print(f"Error getting info: {e}", file=sys.stderr)

    elif args.command == 'preview':
        # Preview logic receiving UDP stream
        udp_port = 49152
        
        try:
            print(f"Starting preview stream on UDP {udp_port}...", file=sys.stderr)
            print("Press Ctrl+C to stop.", file=sys.stderr)
            
            output = sys.stdout.buffer if args.stdout else None
            
            if args.out:
                output = open(args.out, 'wb')
            
            if not output and not args.stdout:
                 print("Receiving stream but not saving/displaying (use --stdout or --out)...", file=sys.stderr)

            for data in camera.stream_preview(port=udp_port):
                if output:
                    output.write(data)
                    output.flush()

        except KeyboardInterrupt:
            print("\nStopping preview...", file=sys.stderr)
        except Exception as e:
            print(f"\nError during preview: {e}", file=sys.stderr)
        finally:
            if args.out and output:
                output.close()

    elif args.command == 'config':
        if args.value:
            print(f"Setting {args.setting} to {args.value}", file=sys.stderr)
            res = camera.set_setting(args.setting, args.value)
            result = res.find('result')
            if result is not None:
                print(f"Result: {result.text}")
            else:
                print(ET.tostring(res, encoding='unicode'))
        else:
            print(f"Getting {args.setting}", file=sys.stderr)
            res = camera.get_setting(args.setting)
            if res is not None:
                # Try to find value
                # Response is typically <camrply><type>...</type><value>...</value></camrply>
                val = res.find('value')
                if val is not None:
                    print(val.text)
                else:
                    # Just dump XML structure if value not found directly
                     print(ET.tostring(res, encoding='unicode'))

    elif args.command == 'image':
        if args.preview:
            print("Capturing preview image...", file=sys.stderr)
            img = camera.get_preview_image()
            if img:
                if args.out:
                    with open(args.out, 'wb') as f:
                        f.write(img)
                    print(f"Saved preview image to {args.out}", file=sys.stderr)
                elif args.stdout:
                     sys.stdout.buffer.write(img)
                     sys.stdout.buffer.flush()
                else:
                     print("Image captured (bytes), but no output specified. Use --out or --stdout.", file=sys.stderr)
            else:
                 print("Failed to capture preview image.", file=sys.stderr)
        else:
            print("Capturing image...", file=sys.stderr)
            camera.capture()
            # In a real app we'd poll for 'sd_access' or content count change
            print("Image capture command sent.", file=sys.stderr)

    elif args.command == 'video':
        if args.action == 'start':
            print("Starting video recording...", file=sys.stderr)
            camera.video_recstart()
        else:
            print("Stopping video recording...", file=sys.stderr)
            camera.video_recstop()

    elif args.command == 'download':
        print(f"Downloading {args.file}...", file=sys.stderr)
        local_file = camera.download_file(args.file, args.dest)
        if local_file:
            print(f"Downloaded to {local_file}")
        else:
            sys.exit(1)

    elif args.command == 'ls':
        print(f"Browsing items {args.start} to {args.start + args.count}...", file=sys.stderr)
        items = camera.browse(start_index=args.start, count=args.count)
        if items:
            print(f"{'ID':<10} {'Title':<20} {'URL'}")
            print("-" * 60)
            for item in items:
                title = item['title'] or 'N/A'
                url = item['url'] or 'N/A'
                print(f"{item['id']:<10} {title:<20} {url}")
        else:
            print("No items found.")

if __name__ == '__main__':
    main()
