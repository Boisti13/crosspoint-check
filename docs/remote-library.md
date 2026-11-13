# Library on another machine

crosspoint-check can run on one machine and check a Calibre library on
another. Only one small file runs next to the library: `agent.py`, which
needs nothing but Python 3.9 or newer. The service reaches it through a
command, normally SSH with a key that can do nothing else.

```text
crosspoint-check  --ssh (restricted key)-->  gate script  -->  agent.py  -->  library
```

## On the machine with the library

1. Copy the agent and the gate:

   ```sh
   install -D -m 755 crosspoint_check/agent.py /usr/local/lib/crosspoint-check/agent.py
   install -m 755 deploy/ssh-gate.sh /usr/local/sbin/crosspoint-check-gate
   ```

2. Edit the last line of `/usr/local/sbin/crosspoint-check-gate` so that
   `--library` names the folder with `metadata.db`. If the library is inside
   a container, put the container command in front, for example
   `exec pct exec 115 -- python3 ...` on Proxmox or
   `exec docker exec -i calibre-web-automated python3 ...` for Docker (the
   agent file must then be inside that container).

3. Allow the service's key, and only for the gate. Add one line to
   `~/.ssh/authorized_keys` of a user who may write to the library:

   ```text
   restrict,command="/usr/local/sbin/crosspoint-check-gate" ssh-ed25519 AAAA... crosspoint-check
   ```

The gate accepts exactly `list`, `get ID` and `put ID SIZE MTIME SHA256`;
anything else is refused. `put` replaces a book only if it still has the size
and modification time that were checked, and only if the upload's checksum
matches.

## On the machine with crosspoint-check

1. Make the key (no passphrase, it is used by a timer) and note the public
   half for step 3 above:

   ```sh
   ssh-keygen -t ed25519 -N "" -C crosspoint-check -f /etc/crosspoint-check/id_ed25519
   ```

2. Record the other machine's host key after checking it there:

   ```sh
   ssh-keyscan -t ed25519 library-host > /etc/crosspoint-check/known_hosts
   ```

3. In `/etc/crosspoint-check/config.toml`:

   ```toml
   [library]
   command = "ssh -i /etc/crosspoint-check/id_ed25519 -o BatchMode=yes -o ConnectTimeout=15 -o UserKnownHostsFile=/etc/crosspoint-check/known_hosts root@library-host"
   ```

4. Test: the same command with `list` at the end prints the books as JSON.

When the other machine can't be reached, the scan stops, the status page says
so, and the next scan catches up.
