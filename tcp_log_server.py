#!/bin/env python3

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

    print(f"\n[+] Connected to {addr[0]}")
    print("[*] Ready for logs (Type commands anytime)...\n")

    # Start Heartbeat
    hb_thread = threading.Thread(target=heartbeat_loop, args=(sock,), daemon=True)
    hb_thread.start()

    sock.settimeout(1.0)
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


# readline completion code

top_cmds = ["cos", "aroma"]

cos_cmds = [
    "bootperf",    # cos bootperf
    "coretrace",   # cos coretrace
    "cpuusage",    # cos cpuusage [c] [p]
    "crashdump",   # cos crashdump [0|1]
    "ctxdump",     # cos ctxdump addr
    "debug",       # cos debug
    "disasm",      # cos disasm addr [words]
    "fault",       # cos fault [cmd]
    "fslogdump",   # cos fslogdump
    "getsym",      # cos getsym addr
    "heapcheck",   # cos heapcheck addr
    "heapdump",    # cos heapdump addr
    "heaps",       # cos heaps
    "help",        # cos help
    "intstats",    # cos intstats [coreId]
    "iodump",      # cos iodump [coreId]
    "iostats",     # cos iostats [coreId]
    "kill",        # cos kill
    "killrestart", # cos killrestart
    "kpanic",      # cos kpanic
    "kstats",      # cos kstats [coreId]
    "launch",      # cos launch hi lo
    "launchex",    # cos launchex tid [args]
    "logdump",     # cos logdump
    "logsave",     # cos logsave
    "memdump",     # cos memdump addr [words]
    "modules",     # cos modules
    "ospanic",     # cos ospanic
    "osstats",     # cos osstats [coreId]
    "runonthread", # cos runonthread [r]
    "sdkversion",  # cos sdkversion
    "setdabr",     # cos setdabr addr [r] [w]
    "setfslog",    # cos setfslog [0|1|2]
    "setiabr",     # cos setiabr addr
    "setword",     # cos setword addr value
    "slowlaunch",  # cos slowlaunch tid [args]
    "stacktrace",  # cos stacktrace addr
    "tcheck",      # cos tcheck
    "threads",     # cos threads
    "timestamp",   # cos timestamp [1|2|3|4]
    "ttrace",      # cos ttrace
]

aroma_cmds = [
    "help",    # aroma help
    "plugins", # aroma plugins
]

aroma_plugins_cmds = [
    "details",    # aroma plugins details
    "heap_usage", # aroma plugins heap_usage
    "help",       # aroma plugins help
    "list",       # aroma plugins list
]

def items_with_prefix(haystack, needle):
    if len(needle) == 0:
        return haystack
    result = []
    for hay in haystack:
        if hay.startswith(needle):
            result.append(hay)
    return result

def get_cos_candidates_for(needle, line, tokens):
    if len(tokens) == 2:
        return items_with_prefix(cos_cmds, needle)
    return None

def get_aroma_candidates_for(needle, line, tokens):
    if len(tokens) == 2:
        return items_with_prefix(aroma_cmds, needle)
    if len(tokens) == 3 and tokens[1] == "plugins":
        return items_with_prefix(aroma_plugins_cmds, needle)
    return None

def get_candidates_for(needle):
    line = readline.get_line_buffer()
    if len(line) == 0:
        return top_cmds

    tokens = line.split(" ")
    if len(tokens) < 2:
        return items_with_prefix(top_cmds, needle)

    match tokens[0]:
        case "cos":
            return get_cos_candidates_for(needle, line, tokens)
        case "aroma":
            return get_aroma_candidates_for(needle, line, tokens)

    return None

def iopshell_completer(text, state):
    candidates = get_candidates_for(text)
    if candidates and state < len(candidates):
        return candidates[state]
    return None

def prepare_readline():

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
    readline.parse_and_bind("tab: complete")

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
            cmd = input("> ")

            with client_lock:
                if current_client:
                    try:
                        current_client.sendall((cmd + "\r\n").encode())
                        pass
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
