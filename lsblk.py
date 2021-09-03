#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Optional, List, Dict, DefaultDict, Union, Any
import json
import subprocess
from collections import defaultdict
import shlex


LINUX_DEV_DIR = "/dev/"
LSBLK_CMD_LINE = ["lsblk", "-b", "-O", "--json"]


class PartitionNotMounted(Exception):
    pass


class BlockDevices:
    def __init__(self) -> None:
        self._json = self._get_json()
        self._devices: List[Device] = list()
        self._types: DefaultDict[str, List[Device]] = defaultdict(list)
        self._removables: DefaultDict[bool, List[Device]] = defaultdict(list)
        self._by_name: Dict[str, Device] = dict()
        self._by_path: Dict[str, Device] = dict()
        self._partitions_by_path: Dict[str, Partition] = dict()

        for dev in self._json:
            device = Device(dev)
            self._devices.append(device)
            self._types[device.type].append(device)
            self._removables[device.rm].append(device)
            self._by_name[device.name] = device
            self._by_path[device.path] = device

            for partition in device.get_partitions():
                self._partitions_by_path[partition.path] = partition


    def _get_json(self) -> Any:
        cmd_res = subprocess.run(LSBLK_CMD_LINE, stdout=subprocess.PIPE)
        return json.loads(cmd_res.stdout.decode())["blockdevices"]


    #TODO plutôt ignore_types: List[str]
    def get_all(self, ignore_loop=True) -> List['Device']:
        """Return a list of all device. Loop devices ignored by default
        """
        if not ignore_loop:
            return self._devices
        else:
            return [dev for dev in self._devices if dev.type != "loop"]


    def get_removables(self) -> List['Device']:
        return self._removables[True]


    def get_types(self) -> List[str]:
        return list(self._types.keys())


    def get_by_type(self, _type: str) -> List['Device']:
        return self._types.get(_type, [])


    def get_by_name(self, name:str) -> 'Device':
        return self._by_name.get(name, None)


    def get_by_path(self, device_path:str) -> 'Device':
        return self._by_path.get(device_path, None)


    def get_partition_by_path(self, part_path:str) -> 'Partition':
        return self._partitions_by_path.get(part_path, None)


    def __repr__(self) -> str:
        return "{}".format(" ".join([device.name for device in self.get_all()]))



class Device:
    @classmethod
    def from_path(cls, device_path: str) -> 'Device':
        return BlockDevices().get_by_path(device_path)


    def __init__(self, _json: Dict[str, Any]) -> None:
        self._json = _json
        self._props = ["name", "model", "vendor", "type", "size", "state", "owner", "group", "serial", "rm", "size"]

        self.name: str
        self.model: str
        self.vendor: str
        self.type: str
        self.size: int
        self.state: str
        self.owner: str
        self.group: str
        self.serial: str
        self.rm: bool

        for prop in self._props:
            setattr(self, prop, self._json[prop])

        self.hrsize = Unit(self.size)
        self.path = LINUX_DEV_DIR + self.name
        self.model = self.model.strip() if self.model else ""
        self.vendor = self.vendor.strip() if self.vendor else ""
        self.ident = self.model or self.serial

        self._partitions: List['Partition'] = list()
        self._partitions_by_name: Dict[str, 'Partition'] = dict()
        self._partitions_by_path: Dict[str, 'Partition'] = dict()

        for part in _json.get("children", []):
            partition = Partition(part)
            self._partitions.append(partition)
            self._partitions_by_name[partition.name] = partition
            self._partitions_by_path[partition.path] = partition


    def get_partitions(self) -> List['Partition']:
        return self._partitions


    def get_partition_by_name(self, name: str) -> 'Partition':
        return self._partitions_by_name.get(name, None)


    def get_partition_by_path(self, path: str) -> 'Partition':
        return self._partitions_by_path.get(path, None)


    def is_removable(self) -> bool:
        return self.rm == True


    def __repr__(self) -> str:
        return "Path: {}  Device: {}  Size: {}  Partitions: {}  Removable: {}  Type: {}".format(self.path, self.ident, self.hrsize.hr, len(self._partitions), self.is_removable(), self.type)


class Partition:
    def __init__(self, _json: Dict[str, str]) -> None:
        self._json = _json
        self._props = ["name", "fstype", "mountpoint", "label", "uuid", "partlabel", "partuuid", "type", "size", "owner", "group"]

        self.name: str
        self.fstype: str
        self.mountpoint: str
        self.label: str
        self.uuid: str
        self.partlabel: str
        self.partuuid: str
        self.type: str
        self.size: str
        self.owner: str
        self.group: str

        for prop in self._props:
            setattr(self, prop, _json[prop])

        self.hrsize = Unit(self.size)
        self.path = LINUX_DEV_DIR + self.name


    def __repr__(self) -> str:
        s = "Partition: {}  Filesystem: {}  Size: {}  Mountpoint: {}".format(self.path, self.fstype, self.hrsize.hr, self.mountpoint or "-")

        if self.label:
            s += "  Label: {}".format(self.label)

        if self.partlabel:
            s += "  Partlabel: {}".format(self.partlabel)

        s += "  uuid: {}".format(self.uuid)

        return s

    def is_mounted(self) -> bool:
        """Retourne True si la partition est montée, False sinon
        """
        return self.mountpoint is not None
    

    def is_listable(self) -> bool:
        if self.is_mounted():
            cmd = "test -r {}; echo \"$?\"".format(self.mountpoint)
            cmd_res = subprocess.run(cmd, stdout=subprocess.PIPE, shell=True)
            return cmd_res.stdout.decode().strip() == "0"
        return False


    def is_empty(self) -> bool:
        """Retourne 'True' si la partition est montée et ne contient aucun fichier, 'False' sinon.
        """
        
        if self.is_listable():
            cmd = ["ls", "-A", self.mountpoint]  # ls -A --almost-all  do not list implied . and ..
            cmd_res = subprocess.run(cmd, stdout=subprocess.PIPE)
            part_content = cmd_res.stdout.decode().strip()

            return not part_content

        return False


class Unit:
    """Représente des bytes en KiB, MiB, etc..
    """
    def __init__(self, bytes: Union[str, int]) -> None:
        self.bytes = int(bytes)
        self.name: str = ""
        self.value: float = 0.0

        self._convert()


    @property
    def hr(self) -> str:
        """Human readable
        """
        return str(self)


    def _convert(self) -> None:
        if self.bytes < 1024:
            self.name = "B"
            self.value = self.bytes
            return

        for unit, mult in [("Kib", 1024), ("MiB", 1024**2), ("GiB", 1024**3), ("TiB", 1024**4), ("PiB", 1024**5)]:
            value = self.bytes / mult

            if 0 < value < 1024:
                self.name = unit
                self.value = value
                return


    def __repr__(self) -> str:
        return "{:.1f} {}".format(self.value, self.name)



if __name__ == "__main__":
    blk = BlockDevices()
    for dev in blk.get_all():
        print(dev)
        for part in dev.get_partitions():
            print("    ", part)
        print()
