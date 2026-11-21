"""
A pretend UPS + PDU + switch on SNMP, so the rack_status example runs without hardware.
Needs snmpsim:  pip install snmpsim pysmi

    python -m panelworks --simulator rack_status            # UDP 127.0.0.1:1161
    python -m panelworks --simulator rack_status --trap     # also send a test trap to UDP 1162

The data is in agent/public.snmprec (read community "public") and agent/private.snmprec
(write community "private"). Values marked "numeric" drift; "writecache" ones can be Set.
"""
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PORT, TRAP_PORT = 1161, 1162


def send_trap(port=TRAP_PORT):
    """Send a 'UPS on battery' trap, like a real UPS would."""
    import pysnmp.hlapi.v3arch.asyncio as h

    async def go():
        eng = h.SnmpEngine()
        tgt = await h.UdpTransportTarget.create(("127.0.0.1", port))
        await h.send_notification(eng, h.CommunityData("public", mpModel=1), tgt, h.ContextData(), "trap",
                                  h.NotificationType(h.ObjectIdentity("1.3.6.1.2.1.33.2.0.1")).add_varbinds(
                                      ("1.3.6.1.2.1.33.1.2.2.0", h.Integer(12)),
                                      ("1.3.6.1.2.1.33.1.2.3.0", h.Integer(41))))
        eng.close_dispatcher()
    asyncio.run(go())
    print(f"Sent a test 'on battery' trap to UDP {port}")


def main():
    if "--trap" in sys.argv:
        send_trap()
        return
    exe = shutil.which("snmpsim-command-responder") or os.path.join(os.path.dirname(sys.executable),
                                                                    "snmpsim-command-responder")
    if not os.path.exists(exe) and not os.path.exists(exe + ".exe"):
        sys.exit("snmpsim isn't installed: pip install snmpsim pysmi")
    cache = tempfile.mkdtemp(prefix="snmpsim-")
    cmd = [exe, f"--data-dir={os.path.join(HERE, 'agent')}", f"--agent-udpv4-endpoint=127.0.0.1:{PORT}",
           f"--cache-dir={cache}"]
    if hasattr(os, "geteuid") and os.geteuid() == 0:           # snmpsim won't run as root
        os.chmod(cache, 0o777)
        cmd += ["--process-user=nobody", "--process-group=nogroup"]
    print(f"Pretend UPS/PDU on UDP 127.0.0.1:{PORT} (communities public / private). Ctrl+C to stop.")
    subprocess.call(cmd)


if __name__ == "__main__":
    main()
