#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# À ce stade, compatible uniquement avec Linux

# TODO: chmod semble ne pas fonctionner
# TODO: Tester que boucliers fonctionnent ...!
# TODO: faire des tests
# TODO: décidement essayer de comprendre ce qui se passe avec label de type gpt

from typing import List, Optional, Tuple

import subprocess
import os
import time

import parted
from parted import Device, Disk, Partition, Geometry

from lsblk import BlockDevices, Partition as LsblkPartition
from utils import get_logger, sudo_exec_as_normal_user


logger = get_logger("wildcopy", "INFO")

ROOT_MOUNTPOINT = "/"
MKE2FS_FILESYSTEMS = ["ext2", "ext3", "ext4"]
DEFAULT_FSTYPE = "ext4"
DEFAULT_LABEL = "msdos"
DEFAULT_MODE = 0o777
DEFAULT_PART_LABEL = "Partition1"


class NotRemovable(Exception):
    """N'est pas un média amovible.
    """

class PartitionNotCreated(Exception):
    """La partition n'a pas encore été ajoutée à la table de partition du device,
    elle n'existe donc pas pour le système d'exploitation
    """

class IsRoot(Exception):
    """La partition est montée sur la raçine du système de fichier
    """

class ChmodFailed(Exception):
    """Le changement de permission sur la partition a échoué.
    """

class PartitionExists(Exception):
    """Il existe déjà une ou plusieurs partitions
    """


class PedPartition:
    @classmethod
    def get_new_partition(cls, device: 'PedDevice') -> Partition:
        """Retourne une nouvelle partition (parted).
        """
        ped_device: Device = device.get_ped_device()
        ped_disk: Disk = device.get_ped_disk()

        geometry = Geometry(start=1, length=ped_device.getLength() - 1, device=ped_device)
        partition = Partition(disk=ped_disk, type=parted.PARTITION_NORMAL, geometry=geometry)

        logger.debug("PedPartition: Nouvelle partition: {}".format(partition))

        return partition


    def __init__(self, ped_part: Partition, device: 'PedDevice') -> None:
        self._device = device
        self._ped_disk: Disk = device.get_ped_disk()

        self._ped_part = ped_part

        self._lsblk_part: Optional[LsblkPartition] = None
        self._refresh_status()


    @property
    def path(self) -> str:
        """Retourne le chemin de la partition
        """
        return self._ped_part.path


    @property
    def mountpoint(self) -> Optional[str]:
        """Retourne le point de montage de la partition
        """
        self._refresh_status()

        return self._lsblk_part.mountpoint if self._lsblk_part else None


    @property
    def fstype(self) -> Optional[str]:
        """Retourne le type du système de fichiers
        """
        return self._ped_part.fileSystem.type if self._ped_part.fileSystem else None


    def is_created(self) -> bool:
        """'True' si la partition a été ajoutée à la table de partitions
        """
        return self._ped_part.number != -1


    def is_mounted(self) -> bool:
        """Retourne 'True' si l partition est montée, 'False' sinon
        """
        self._refresh_status()

        return self._lsblk_part.is_mounted() if self._lsblk_part else False


    def umount(self) -> None:
        """Démonte la partition
        """
        logger.debug("Démontage de {}".format(self.path))

        if self.is_mounted():
            subprocess.run(["udisksctl", "unmount", "-b", self.path])
            logger.info("Démonté: {}".format(self.path))


    def mount(self) -> str:
        """Monte la partition si pas encore montée, en utilisant 'udiskctl'. Tente de monter sur l'utilisateur ayant invoqué sudo. Retourne le point de montage
        """
        logger.debug("Montage de {}".format(self.path))

        if not self.is_mounted():
            sudo_exec_as_normal_user("udisksctl mount -b {}".format(self.path))
            logger.info("{} montée sur {}".format(self.path, self.mountpoint))

        return self.mountpoint


    def delete(self) -> None:
        """Supprime la partition de la table de partition, sauf si est montée sur ROOT_MOUNTPOINT
        """
        logger.debug("Suppression de la partition {}".format(self))

        self._check_before()

        if self.is_mounted():
            self.umount()

        self._ped_disk.deletePartition(self._ped_part)
        self._ped_disk.commit()

        logger.info("Partition supprimée: {}".format(self))
        # supprime de la liste des partitions de ped_disk
        self._device._partitions.remove(self)



    def format(self, fstype: str, partlabel: Optional[str]=None) -> None:
        """Formate la partition
        """
        logger.info("Formatage de  {}".format(self))

        self._check_before()

        if self.is_mounted():
            self.umount()

        partlabel = self._get_label(partlabel)

        if fstype in MKE2FS_FILESYSTEMS:
            subprocess.run(["mke2fs", "-t", fstype, "-L", partlabel, "-F", self.path])
            time.sleep(0.5) # semble nécessaire sinon udisksctl veut pas la monter
            logger.debug("Partition formatée {}".format(self))


    def chmod(self, mode: int=0o777) -> None:
        """Change le mode du point de montage. N'est pas récursif.
        """
        logger.debug("Changement du mode: {} sur {}".format(mode, self))

        if self.is_mounted():
            try:
                os.chmod(self.mountpoint, mode=mode)
                logger.debug("Mode changé: {} sur {}".format(mode, self.path))
            except Exception as e:
                msg = "Erreur durant chmod: {}".format(e)
                logger.warning(msg)
                raise ChmodFailed("chmod {} sur {} a échoué".format(mode, self.path))
        else:
            msg = "La partition {} n'est pas montée, chmod pas possible".format(self.path)
            logger.warning(msg)
            raise ChmodFailed(msg)


    def _check_before(self) -> None:
        if self.mountpoint is ROOT_MOUNTPOINT:
            raise IsRoot("La partition est montée sur la raçine du sytème de fichiers")

        if not self.is_created():
            raise PartitionNotCreated("La partition doit être ajoutée à la table des partitions")


    def _refresh_status(self) -> None:
        """Rafraîchit les infos de la partition
        Peut ne pas y en avoir, si partition fraîchement créée
        mais pas encore écrite dans la table de partition
        """
        self._lsblk_part = BlockDevices().get_partition_by_path(self.path)


    def _get_label(self, partlabel: Optional[str]) -> str:
        """Si pas de label passe label par défault.
        Tronque la label à 12 (max 16 bytes pour mk2efs)
        """
        if not partlabel:
            partlabel = DEFAULT_PART_LABEL

        partlabel = partlabel[:12]

        return partlabel


    def __repr__(self) -> str:
        return "Partition:  path: {path}  mountpoint: {mountpoint} fstype: {fstype}".format(path=self.path, mountpoint=self.mountpoint, fstype=self.fstype)



class PedDevice:
    """Un support ('device') manipulable par pyparted
    """
    def __init__(self, path: str, force: bool=False):
        self.path = path
        self._force_creation = force # si True crée une nouvelle table de partition si la partition
                                     # existante semble endommagée ou absente

        logger.debug("PedDevice: path: {} _force_creation: {}".format(self.path, self._force_creation))

        self._lsblk_dev = BlockDevices().get_by_path(self.path)

        if not self._lsblk_dev.is_removable():
            msg = "{} n'est pas un media amovible. Interruption.".format(self._lsblk_dev.path)
            logger.error(msg)
            raise NotRemovable(msg)

        self._ped_dev = parted.getDevice(self.path)

        logger.debug("Parted device: {}".format(self._ped_dev))

        self._ped_disk: Disk
        self._partitions: List[PedPartition]
        self._get_disk_and_partitions()


    def get_partitions(self) -> List[PedPartition]:
        """Retourne la liste des partition
        """
        return self._partitions


    def get_partition(self, partition_path:str) -> Optional[PedPartition]:
        """Retourne la partition dont le chemin est 'partition_path', 'None' sinon
        """
        for partition in self.get_partitions():
            if partition.path == partition_path:
                return partition

        return None


    def partition_device(self) -> PedPartition:
        """ Démonte et supprime toutes les partition, recrée une table de partition et
        crée un partition qui prend toute la place disponible sur le media
        """

        for partition in self.get_partitions():
            partition.umount()
            partition.delete()

        # nouvelle table de partitions
        self._ped_disk = self._get_fresh_disk()

        partition = self._add_new_partition()

        return partition


    def format_partition(self, partition: PedPartition, fstype: str, partlabel: Optional[str]=None, mount: bool=True, mode: int=None) -> None:
        """ ... Pas de check du mode
        """
        if partition.is_mounted():
            partition.umount()

        partition.format(fstype=fstype, partlabel=partlabel)

        if mount:
            partition.mount()

        mode = mode if mode else DEFAULT_MODE

        try:
            partition.chmod(mode)
        except ChmodFailed:
            pass


    def get_ped_device(self) -> Device:
        """Retourne le 'device' parted sous-jacent
        """
        return self._ped_dev


    def get_ped_disk(self) -> Disk:
        """Retourne le 'disk' parted sous-jacent
        """
        return self._ped_disk


    def is_removable(self) -> bool:
        """Retourne 'True' si le dispositif est amovible, 'False' sinon
        """
        return self._lsblk_dev.is_removable()


    def _add_new_partition(self) -> PedPartition:
        """Crée et ajoute un partition unique à une table de partitions vide.
        """
        if len(self.get_partitions()):
            raise Exception("Impossible de créer une partition unique s'il y a déjà des partitions.")

        ped_part = PedPartition.get_new_partition(self)

        self._ped_disk.addPartition(ped_part, self._ped_dev.optimalAlignedConstraint)
        self._ped_disk.commit()

        logger.info("Partition ajoutée à la table des partitions: {}".format(ped_part))
        # On rafraîchir après ajout pour avoir nouvelle liste des partitions
        # parted disk ne mets pas sa liste de partitions à jour après ajout
        self._get_disk_and_partitions()

        new_partition = self.get_partition(ped_part.path)

        return new_partition


    def _get_fresh_disk(self) -> Disk:
        """Retourne une nouvelle instance de Disk (parted). A pour effet d'écraser la table de partition
        """
        logger.debug("Création d'une nouvelle table de partitions")

        return parted.freshDisk(self._ped_dev, DEFAULT_LABEL)


    def _get_disk_and_partitions(self) -> None:
        """Instancie le disk parted et les partitions ('PedPartition')
        Nécessaire de le refaire après ajout d'une partition dans la table des partitions,
        le disk parted semble ne pas être correctement mis à jour
        """
        try:
            # D'abord non destructif
            self._ped_disk = parted.newDisk(self._ped_dev)
        except parted._ped.DiskException as e:               # Problème, label absent par exemple
            logger.debug(f"Problème lors de la lecture du media: {e}")
            if self._force_creation:
                self._ped_disk = self._get_fresh_disk()          # Si self._force_creation, on crée une nouvelle table de partitions
            else:
                raise Exception(f"Problème lors de la lecture du media: {e}")

        self._partitions = [PedPartition(part, self) for part in self._ped_disk.partitions]
        logger.debug("Partitions sur le media: {}".format(" ".join([str(p) for p in self._partitions])))



# Fonction "de secours" pour avoir un media propre
def partition_formatatage_rapide_sdb(device_path: Optional[str]=None) -> None:
    """Partitionnement - formatage rapide pour reset
    """
    path = device_path or "/dev/sdb"
    fstype = "ext4"
    partlabel = "TestPart"

    ped_dev = parted.getDevice(path)

    # D'abord démonter et supprimer les partitions (si pas démonté, le système ne sais pas que changements)
    try:
        ped_disk = parted.newDisk(ped_dev)
        for partition in ped_disk.partitions:
            print("Démontage de {}".format(partition.path))
            subprocess.run(["udisksctl", "unmount", "-b", partition.path])

        # faut supprimer toutes les partitions avant de faire freshDisk, sinon plus rien
        print("Suppression de toutes les partitions")
        for part in ped_disk.partitions:
            ped_disk.deletePartition(part)
        ped_disk.commit()
    except parted._ped.DiskException as e:
        print(e)
        # raise(e)

    new_disk = parted.freshDisk(ped_dev, "gpt")

    new_geom = parted.Geometry(start=1, length=ped_dev.getLength() - 1, device=ped_dev)
    new_fs = parted.FileSystem(type=fstype, geometry=new_geom)
    new_part = parted.Partition(disk=new_disk, type=parted.PARTITION_NORMAL, fs=new_fs, geometry=new_geom)

    new_disk.addPartition(new_part, ped_dev.optimalAlignedConstraint)
    new_disk.commit()


    print("Formatage de la partition {}".format(new_part.path))
    subprocess.run(["mke2fs", "-t", fstype, "-L", partlabel, "-F", new_part.path])


    print("Montage")
    time.sleep(0.5) # semble nécessaire
    subprocess.run(["udisksctl", "mount", "-b", new_part.path])


if __name__ == "__main__":
    # path = "/dev/sdb"
    # device = PedDevice(path)
    # # partition = device.partition_device()
    # # partition = device.get_partition("/dev/sdb1")
    # partition = device.partition_device()
    # partition.format(fstype="ext4")
    # partition.mount()

    # partition_formatatage_rapide_sdb()
    pass
