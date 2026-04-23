#!/usr/bin/env python3

import atexit
import os
import readline
import socket
import sys
import threading
import time

# --- Configuration ---
TCP_PORT = 7965
UDP_BEACON_PORT = 4445

# Global state
current_client = None
client_lock = threading.Lock()

def udp_broadcaster():
    """Beacon so Wii U finds us automatically"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    msg = b"WIIU_TCP_SYSLOG_BEACON_V1"

    print(f"[*] UDP Beacon active on port {UDP_BEACON_PORT}")

    while True:
        # Only broadcast if no one is connected
        if current_client is None:
            try:
                sock.sendto(msg, ('<broadcast>', UDP_BEACON_PORT))
            except:
                pass
        time.sleep(0.5)

def heartbeat_loop(sock):
    """Sends a hidden ping every second to keep Wii U connection alive."""
    while True:
        with client_lock:
            # If socket is no longer the active client, stop thread
            if sock != current_client:
                break

        try:
            time.sleep(1.0)
            # Send a NULL byte. The Wii U logic ignores this but resets watchdog.
            sock.sendall(b'\x00')
        except:
            # If send fails, the main handler will catch it eventually,
            # or we can force close here.
            break


def handle_client(sock, addr):
    """Reads logs from Wii U and prints them"""
    global current_client

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

    print(f"\n[+] Connected to {addr[0]}")
    print("[*] Ready for logs (Type commands anytime)...\n")

    # Start Heartbeat
    hb_thread = threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True)
    hb_thread.start()

    sock.settimeout(0.5)
    rx_buffer = ""

    while True:
        try:
            data = sock.recv(4096)
            if not data:
                print("[!] Remote closed connection.")
                break

            # Decode and process lines
            text = data.decode('utf-8', errors='replace')

            # Filter NULL bytes (Heartbeat artifacts)
            text = text.replace('\x00', '')

            rx_buffer += text

            while "\r" in rx_buffer:
                line, rx_buffer = rx_buffer.split("\r", 1)
                # Print immediately
                print(f"{line}")

        except socket.timeout:
            if rx_buffer:
                print(f"{rx_buffer}", end="", flush=True)
                rx_buffer = ""
            continue
        except Exception as e:
            print(f"[!] Connection Error: {e}")
            break

    print(f"[-] Disconnected from {addr[0]}")
    print(f"Waiting for new connections")

    with client_lock:
        if current_client == sock:
            current_client = None
    try:
        sock.close()
    except: pass

def server_listener():
    """Waits for incoming TCP connections"""
    global current_client

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server.bind(('0.0.0.0', TCP_PORT))
    except Exception as e:
        print(f"[!] Fatal: Could not bind port {TCP_PORT}. {e}")
        return

    server.listen(1)
    print(f"[*] TCP Server listening on {TCP_PORT}")

    while True:
        try:
            client, addr = server.accept()

            current_client = client

            print(f"[*] Server connected on port {TCP_PORT}")
            # Handle this client in this thread (blocks until disconnect)
            handle_client(client, addr)

        except Exception as e:
            print(f"[!] Server Error: {e}")


## ---------------------------------- ##
## Start of readline completion code. ##
## ---------------------------------- ##
command_map = {
    "aroma": {
        "help": None,
        "plugins": {
            "details"    : None, # aroma plugins details
            "heap_usage" : None, # aroma plugins heap_usage
            "help"       : None, # aroma plugins help
            "list"       : None, # aroma plugins list
        },
    },
    "cos": {
        "bootperf"    : None, # cos bootperf
        "coretrace"   : None, # cos coretrace
        "cpuusage"    : None, # cos cpuusage [c] [p]
        "crashdump"   : None, # cos crashdump [0|1]
        "ctxdump"     : None, # cos ctxdump addr
        "debug"       : None, # cos debug
        "disasm"      : None, # cos disasm addr [words]
        "fault"       : None, # cos fault [cmd]
        "fslogdump"   : None, # cos fslogdump
        "getsym"      : None, # cos getsym addr
        "heapcheck"   : None, # cos heapcheck addr
        "heapdump"    : None, # cos heapdump addr
        "heaps"       : None, # cos heaps
        "help"        : None, # cos help
        "intstats"    : None, # cos intstats [coreId]
        "iodump"      : None, # cos iodump [coreId]
        "iostats"     : None, # cos iostats [coreId]
        "kill"        : None, # cos kill
        "killrestart" : None, # cos killrestart
        "kpanic"      : None, # cos kpanic
        "kstats"      : None, # cos kstats [coreId]
        "launch"      : None, # cos launch hi lo
        "launchex"    : None, # cos launchex tid [args]
        "logdump"     : None, # cos logdump
        "logsave"     : None, # cos logsave
        "memdump"     : None, # cos memdump addr [words]
        "modules"     : None, # cos modules
        "ospanic"     : None, # cos ospanic
        "osstats"     : None, # cos osstats [coreId]
        "runonthread" : None, # cos runonthread [r]
        "sdkversion"  : None, # cos sdkversion
        "setdabr"     : None, # cos setdabr addr [r] [w]
        "setfslog"    : None, # cos setfslog [0|1|2]
        "setiabr"     : None, # cos setiabr addr
        "setword"     : None, # cos setword addr value
        "slowlaunch"  : None, # cos slowlaunch tid [args]
        "stacktrace"  : None, # cos stacktrace addr
        "tcheck"      : None, # cos tcheck
        "threads"     : None, # cos threads
        "timestamp"   : None, # cos timestamp [1|2|3|4]
        "ttrace"      : None, # cos ttrace
    },
    "iosu": {
        "help"     : None,
        "reboot"   : None,
        "reload"   : None,
        "shutdown" : None,
    },
}

def get_candidates_for(text, tokens):
    # first navigate using all tokens except the last
    node = command_map
    for token in tokens[:-1]:
        if token in node:
            node = node[token]
            if node is None:
                return []
        else: # if user typed garbage, return no candidates
            return []
    # all keys that start with text are candidates
    return [x for x in node.keys() if x.startswith(text)]

def iopshell_completer(text, state):
    tokens = readline.get_line_buffer().split(" ")
    candidates = get_candidates_for(text, tokens)
    if candidates and state < len(candidates):
        return candidates[state]
    return None
## -------------------------------- ##
## Enf of readline completion code. ##
## -------------------------------- ##

def prepare_readline():

    readline.read_init_file()

    hist_filename = ".wiiu_shell_history"
    try:
        from xdgenvpy.xdgenv import XDG
        xdg = XDG()
        # place history file in ~/.config/
        hist_path = os.path.join(xdg.XDG_CONFIG_HOME, hist_filename)
    except:
        # fallback is local directory
        hist_path = hist_filename

    try:
        readline.read_history_file(hist_path)
        readline.set_history_length(1000)
    except FileNotFoundError:
        pass
    atexit.register(readline.write_history_file, hist_path)
    readline.set_auto_history(True)

    readline.set_completer_delims(" ")
    readline.set_completer(iopshell_completer)

if __name__ == "__main__":
    prepare_readline()

    # 1. Start UDP Beacon (Background)
    threading.Thread(target=udp_broadcaster, daemon=True).start()

    # 2. Start TCP Server (Background)
    threading.Thread(target=server_listener, daemon=True).start()

    # 3. Main Thread: Handle User Input
    try:
        while True:
            # Simple input loop
            cmd = input()

            with client_lock:
                if current_client:
                    try:
                        current_client.sendall((cmd + "\r\n").encode())
                    except:
                        print("[!] Failed to send command (Connection dead?)")
                        # Force close to reset state
                        try: current_client.close()
                        except: pass
                        current_client = None
                else:
                    print("[!] Not connected to Wii U")

    except (KeyboardInterrupt, EOFError):
        print("\n[*] Exiting...")
        sys.exit(0)
