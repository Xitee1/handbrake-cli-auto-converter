To integrate the program into Home Assistant, here's an example configuration:

```yaml
# Handbrake-Helper
switch:
  - platform: template
    switches:
      pve_test_handbrake_helper_switch:
        unique_id: pve_test_handbrake_helper_switch
        friendly_name: "PVE Test - Handbrake-Helper - Konvertierung"
        turn_on:
          action: rest_command.pve_test_handbrake_helper_start
        turn_off:
          action: rest_command.pve_test_handbrake_helper_stop
        value_template: "{{ is_state('sensor.pve_test_handbrake_helper_status', 'running') and is_state('sensor.pve_test_handbrake_helper_stoppen', 'False') }}"

rest_command:
  pve_test_handbrake_helper_start:
    url: "http://x.x.x.x:5000/api/start"
    method: post
    verify_ssl: false
  pve_test_handbrake_helper_stop:
    url: "http://x.x.x.x:5000/api/stop"
    method: post
    verify_ssl: false

rest:
  - resource: "http://x.x.x.x:5000/api/status"
    scan_interval: 3
    sensor:
      - name: "PVE Test - Handbrake-Helper - Status"
        unique_id: "pve_test_handbrake_helper_status"
        value_template: "{{ value_json.status }}"

      - name: "PVE Test - Handbrake-Helper - Aktuelle Datei"
        unique_id: "pve_test_handbrake_helper_current_file"
        value_template: "{{ value_json.current_file }}"

      - name: "PVE Test - Handbrake-Helper - Wird gestoppt"
        unique_id: "pve_test_handbrake_helper_scheduled_stop"
        value_template: "{{ value_json.scheduled_stop }}"

      - name: "PVE Test - Handbrake-Helper - Konvertierte Dateien"
        unique_id: "pve_test_handbrake_helper_converted_file_amount"
        state_class: measurement
        value_template: "{{ value_json.source_files_processed }}"

# Host-PC
# To make this work, you must have an ssh key file in the /config/.ssh directory in home assistant and have added the public key to the file ~/.ssh/authorized_keys on the handbrake host.
# To generate a key, execute the ssh-keygen command.
shell_command:
  power_off_pve_test: ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -o LogLevel=quiet -i /config/.ssh/id_rsa root@x.x.x.x "poweroff"
```