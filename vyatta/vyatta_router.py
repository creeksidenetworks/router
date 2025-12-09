# Edgerouter/VyOS management scripts
# Copyright (c) 2024 Jackson Tong, Creekside Networks LLC.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import  os
import  re
import  sys
import  paramiko

from    datetime    import datetime
import  time
from    utility.confirm import get_confirmation
from    utility.ux      import Colors
from    update.router_id import get_router_id

VYATTA_OP_CMD_WRAPPER = "/opt/vyatta/bin/vyatta-op-cmd-wrapper"

class VyattaRouter:
    def __init__(self, hostname, username, password=None, port=None):
        self.dnsname        = hostname
        self.username       = username
        self.password       = password
        self.port           = port
        self.ssh_client     = None
        self.is_connected   = False
        self.hardware       = None
        self.firmware       = None
        self.model          = "VyOS"
        self.sftp_client    = None
        self.id             = None

        self._connect()

    def _connect(self):
        #paramiko.util.log_to_file(filename="log/ssh.log")
        paramiko.transport.Transport._preferred_pubkeys = (
            "ssh-ed25519",
            "ecdsa-sha2-nistp256",
            "ecdsa-sha2-nistp384",
            "ecdsa-sha2-nistp521",
            "ssh-rsa",
            "rsa-sha2-512",
            "rsa-sha2-256",
            "ssh-dss",
        )        

        # load ssh config under home
        ssh_config_file = os.path.expanduser('~/.ssh/config')
        if os.path.exists(ssh_config_file):
            ssh_config = paramiko.SSHConfig()
            with open(ssh_config_file) as f:
                ssh_config.parse(f)

            # Match the given hostname against the SSH config file
            host_config = ssh_config.lookup(self.dnsname)

            # Apply settings from ~/.ssh/config if they are not explicitly provided
            if 'hostname' in host_config:
                self.dnsname = host_config['hostname']
            if 'user' in host_config and not self.username:
                self.username = host_config['user']
            if 'port' in host_config and not self.port:
                self.port = int(host_config['port'])
            if 'identityfile' in host_config and not self.password:
                self.password = None  # Use SSH keys instead of password

        # Set default port if not provided
        if not self.port:
            self.port = 22  

        # create ssh client
        self.ssh_client = paramiko.SSHClient()
        self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        # Attempt to connect until successful
        while True:
            try:                
                # If password is provided, use it; otherwise, try to connect using keys or other methods.
                if self.password:
                    #print (f"{self.dnsname} | {self.username} | {self.password} | {self.port}")
                    self.ssh_client.connect(
                        hostname=self.dnsname,
                        username=self.username,
                        password=self.password,
                        port=self.port,
                        timeout=10,
                        look_for_keys=False,
                        allow_agent=False
                    )
                else:
                    self.ssh_client.connect(
                        hostname=self.dnsname,
                        username=self.username,
                        port=self.port,
                        timeout=10,
                        look_for_keys=True,
                        allow_agent=True
                    )
                
                self.sftp_client = self.ssh_client.open_sftp()
                self.is_connected = True
                print(f"SSH connection established with {self.dnsname}.")

                # validate if it is an EdgeRouter or VyOS router
                stdin, stdout, stderr = self.ssh_client.exec_command("if [ -f /opt/vyatta/etc/version ]; then [ -f /etc/version ] && cat /etc/version || cat /opt/vyatta/etc/version; else echo 'Unknown'; fi")
                version_info = stdout.read().decode("utf8").rstrip()

                pattern = r"^EdgeRouter\.ER-([\w-]+)\.(v\d+\.\d+\.\d+(?:-hotfix\.\d)?)(?=\.\d)"
                match = re.search(pattern, version_info)

                if match:
                    self.hardware=match.group(1)
                    self.firmware=match.group(2)
                    # identify the EdgeRouter model
                        # Execute the "show version" command
                    stdin, stdout, stderr = self.ssh_client.exec_command(f"{VYATTA_OP_CMD_WRAPPER} show version")
                    version_info = stdout.read().decode("utf8").rstrip()

                    # Parse the output to find the hardware model and firmware version
                    # Parse the output to find the hardware model
                    match = re.search(r"HW model:\s*(.+)", version_info)

                    if match:
                        self.model = match.group(1).strip()
                    else:
                        self.model="EdgeRouter (Unknown)"

                elif version_info.startswith("Version:"):
                    self.model="VyOS"
                    self.hardware=""
                    self.firmware=version_info.split(":")[1].strip()
                else:
                    print(f"\nThis script only supports EdgeRouter or VyOS router\n")        
                    sys.exit(1)

                # Retrieve the router's hostname
                stdin, stdout, stderr = self.ssh_client.exec_command("hostname")
                self.hostname = stdout.read().decode().strip()

                print(f"\n{self.hostname} | {self.model} | {self.hardware} | {self.firmware}\n")

                #self.router_id = get_router_id(self.ssh_client)
                return True

            except Exception as e:
                print(f"Failed to connect to {self.dnsname}: {e}")
                # If connection fails, prompt for new input
                print("\nPlease re-enter the connection details:")
                self.dnsname   = input(f"  Hostname [{Colors.GREEN}{self.dnsname}{Colors.RESET}]: ") or self.dnsname
                self.username   = input(f"  Username [{Colors.GREEN}{self.username}{Colors.RESET}]: ") or self.username
                self.password   = input("  Password (Empty to use ssh key): ") or None
                self.port       = input(f"  SSH Port [{Colors.GREEN}{self.port}{Colors.RESET}]: ") or self.port

    def close(self):
        if self.ssh_client:
            self.ssh_client.close()
            print(f"SSH connection to {self.dnsname} closed.")

    def run_op_cmd(self, command):
        """
        Run an vyatta operational command
        :param command: vyatta operational command, str type
        :returns: command output
        """
        return self.run_os_cmd(f"{VYATTA_OP_CMD_WRAPPER} {command}")

    def run_os_cmd(self, command, echo=False):
        """
        Execute a command on the remote server and print the output based on echo flag
        :param command: Command to execute
        :param echo: If True, print output in real-time; if False, print after command finishes
        :return: Tuple of (output, error)
        """
        transport = self.ssh_client.get_transport()
        channel = transport.open_session()
        channel.exec_command(command)

        output = []
        error = []

        if echo:
            while True:
                time.sleep(0.1)
                if channel.recv_ready():
                    line = channel.recv(1024).decode()
                    print(line, end='')
                    output.append(line)
                if channel.recv_stderr_ready():
                    line = channel.recv_stderr(1024).decode()
                    print(line, end='')
                    error.append(line)
                if channel.exit_status_ready():
                    break
        else:
            output = channel.recv(1024).decode()
            error = channel.recv_stderr(1024).decode()

        channel.close()
        return ''.join(output), ''.join(error)
    
    def backup(self, local_backup_dir):
        try:
            print(f"  Backup the router to \"{local_backup_dir}\".")
            # Generate timestamp for the backup file
            timestamp = datetime.now().strftime('%y%m%d%H%M%S')
            backup_filename = f"backup_{self.dnsname}_{timestamp}.tar.gz"
            # Create a temporary file for the backup on the router
            stdin, stdout, stderr = self.ssh_client.exec_command("mktemp")
            remote_backup_file = stdout.read().decode().strip()
            if not remote_backup_file:
                raise Exception("  - Failed to create a temporary file on the router.")

            print(f"  - Created temporary backup file at {remote_backup_file} on the router.")

            # Create a tar.gz archive of the /config directory
            create_tar_cmd = f"sudo tar -czf {remote_backup_file} -C / config"
            self.ssh_client.exec_command(create_tar_cmd)
            print(f"  - Created backup archive at {remote_backup_file} on the router.")

            # Ensure the local backup directory exists
            os.makedirs(local_backup_dir, exist_ok=True)

            # Download the backup file to the local directory
            local_backup_file = os.path.join(local_backup_dir, backup_filename)
            self.sftp_client.get(remote_backup_file, local_backup_file)
            print(f"  - Downloaded backup to {local_backup_file}.")

            # Delete the remote temporary backup file
            self.ssh_client.exec_command(f"rm {remote_backup_file}")
            print(f"  - Cleanup remote router.")
        except Exception as e:
            print(f"  - Backup failed: {e}")

    def restore(self, local_backup_file):
        try:
            # Upload the backup file to the router
            remote_backup_file = "/tmp/backup_config_restore.tar.gz"
            self.sftp_client.put(local_backup_file, remote_backup_file)
            print(f"Uploaded backup archive to {remote_backup_file} on the router.")

            # Extract the backup archive on the router
            extract_tar_cmd = f"sudo tar -xzf {remote_backup_file} -C /"
            self.ssh_client.exec_command(extract_tar_cmd)
            print(f"Restored backup from {remote_backup_file}.")

            # Delete the remote backup file after restoration
            self.ssh_client.exec_command(f"rm {remote_backup_file}")
            print(f"Removed backup archive from the router after restoration.")
        except Exception as e:
            print(f"Restore failed: {e}")

    def upload(self, local_path, remote_path, echo=False, permission="0644"):
        """
        Upload a file to the router
        :param local_path: Path to the local file
        :param remote_path: Path on the router where the file should be uploaded
        :param echo: If True, print output in real-time; if False, print after command finishes
        :param permission: File permission to set after upload (e.g., '755')
        """
        try:
            # Extract the directory path from the remote_path
            remote_dir = os.path.dirname(remote_path)

            # Check if the remote directory exists, if not, create it
            stdin, stdout, stderr = self.ssh_client.exec_command(f"if [ ! -d {remote_dir} ]; then sudo mkdir -p {remote_dir}; fi")
            stderr_output = stderr.read().decode().strip()
            if stderr_output:
                raise Exception(f"Failed to create directory {remote_dir} on the router: {stderr_output}")

            # Create a temporary file on the router
            stdin, stdout, stderr = self.ssh_client.exec_command("mktemp")
            temp_remote_path = stdout.read().decode().strip()
            if not temp_remote_path:
                raise Exception("Failed to create a temporary file on the router.")

            # Upload the file to the temporary location
            self.sftp_client.put(local_path, temp_remote_path)

            # Move the file to the desired location with sudo
            self.ssh_client.exec_command(f"sudo mv {temp_remote_path} {remote_path}")

            # Change the file permission if specified
            self.ssh_client.exec_command(f"sudo chmod {permission} {remote_path}")

            # Make the file executable if it has a .sh or .py suffix
            if remote_path.endswith(".sh") or remote_path.endswith(".py"):
                self.ssh_client.exec_command(f"sudo chmod 0755 {remote_path}")

            if echo:
                print(f"    - Uploaded {os.path.basename(local_path)} to {remote_dir}/ successfully.")
        except Exception as e:
            if echo:
                print(f"\n  *** Failed to upload {os.path.basename(local_path)} to {remote_dir}: {e}")
                
    def download(self, remote_path, local_path=None, echo=False):
        """
        Download a file from the router
        :param remote_path: Path to the file on the router
        :param local_path: Path on the local machine where the file should be downloaded
        """
        try:
            if local_path is None:
                # Read and return the content of the remote file
                with self.sftp_client.open(remote_path, 'r') as remote_file:
                    content = remote_file.read()
                return content.decode('utf-8')  # Decode the binary content to a string
            else:
                # Ensure the local directory exists
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                # Download the file to the local path
                self.sftp_client.get(remote_path, local_path)
                if echo:
                    print(f"\n  o Downloaded {remote_path} to {local_path} successfully.")
        except Exception as e:
            if echo:
                print(f"  *** Failed to download {remote_path}: {e}")
            return None
        
    def _send_interactive_command(self, shell, command, timeout=5, delay=0.1, echo=True, indent=2):
        spaces = " " * (indent+2)

        shell.send(command + '\n')
        output = ""
        start_time = time.time()

        # Define the regex patterns to detect the shell prompts
        #normal_prompt_pattern = re.compile(rf"{self.username}@{self.hostname}:.+\$")
        normal_prompt_pattern = re.compile(rf"{self.username}@.*:.+\$")
        #config_prompt_pattern = re.compile(rf"{self.username}@{self.hostname}#")
        config_prompt_pattern = re.compile(r"\[edit\]")

        while True:
            try:
                response = shell.recv(1024).decode('utf-8')
                output += response
                if config_prompt_pattern.search(response) or normal_prompt_pattern.search(response):
                    break
            except paramiko.ssh_exception.SSHException:
                pass
            
            time.sleep(delay)

            if time.time() - start_time > timeout:
                raise TimeoutError(f"Prompt not detected within {timeout} seconds after command: {command}")

        if echo:
            # Print the response line by line, excluding lines that match the exclusion patterns and empty lines
            exclusion_patterns = [
                #re.compile(rf"{self.username}@{self.hostname}#"),
                #re.compile(rf"{self.username}@{self.hostname}:.+\$"),
                re.compile(rf"{self.username}@.*#"),
                re.compile(rf"{self.username}@.*:.+\$"),
                re.compile(r"\[edit\]")
            ]

            for line in output.splitlines():
                if line.strip() and not any(pattern.match(line) for pattern in exclusion_patterns):
                    print(f"{spaces}> ",line)

    def config(self, commands, timeout=15, indent=2):

        spaces = " " * indent
        """
        Execute configuration commands interactively and print output after each command execution.
        
        :param commands: List of configuration commands to execute.
        :param timeout: Timeout in seconds to wait for the prompt after each command.
        """
        if not self.is_connected:
            raise Exception("SSH connection not established.")

        # Open an interactive shell session
        shell = self.ssh_client.invoke_shell(width=1024, height=10240)
        shell.settimeout(30)

        # Read the initial prompt
        initial_prompt = shell.recv(1024).decode('utf-8')
        #print(initial_prompt)
        
        print(f"\n{spaces}* Enter configuration mode...")
        self._send_interactive_command(shell, "configure", timeout=timeout, echo=False, indent=indent)

        print(f"\n{spaces}* Send configuration commands...")
        for command in commands:
            self._send_interactive_command(shell, command, timeout, delay=0.2, echo=True, indent=indent)

        if (get_confirmation(f"\n{spaces}* Commit changes?", strict=True)):
            self._send_interactive_command(shell, "commit; save", timeout=300, echo=False, indent=indent)
            self._send_interactive_command(shell, "exit", timeout=timeout, echo=False, indent=indent)
        else:
            print(f"\n{spaces}* Discard changes...")
            self._send_interactive_command(shell, "exit discard", timeout=timeout, echo=False, indent=indent)

        # Close the shell session
        shell.close()

        return True

