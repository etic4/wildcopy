#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# TODO: garder à l'esprit que readline pas disponible sur macos
# TODO: intercepter ctrl+c
# TODO: aérer l'interface

from typing import List, Tuple, Optional
import sys, os
import cmd
import shlex

import readline #! pour historique etc


import click
from lsblk import BlockDevices, Device




def lsblk_list(removables: bool=True) -> List[Device]:
    bdev = BlockDevices()
    if removables:
        return bdev.get_removables()
    else:
        return bdev.get_all()

@click.group()
def cli():
    pass



@cli.command()
@click.option("-r", "--removables", is_flag=True, default=True)
def devices(removables: bool) -> List[Device]:
    """Liste les devices
    """
    for dev in lsblk_list(removables):
        print(dev)


intro_string = """Copie le contenu du répertoire spécifié sur le support amovible sélectionné. Le support de destination sera formaté selon le format spécifié. Le support sera partitionné s'il comprend plus d'une partition.

Exécuter "help" pour afficher la liste des commandes.
Exécuter "help <commande>" pour obtenir de l'aide sur une commande.

"""

class Wcp(cmd.Cmd):
    intro = intro_string
    prompt = "(wcp)> "

    def __init__(self) -> None:
        super().__init__()

        self._device: str = ""
        self._dirpath: str = ""
        self._format: bool = True
        self._fstype = "ext2"

        self.intro += self._get_params()


    def default(self, arg: str) -> Optional[bool]:
        if arg == "EOF":
            # ctrl+d, on quitte
            self.stdout.write("\n")
            return True

        print("Commande inconnue: {}".format(arg))

        return None

    def do_devices(self, arg: str) -> None:
        """Liste les supports amovibles connectés.
        """
        for i, rem in enumerate(lsblk_list()):
            print("{}  ({})  {}".format(rem.path, rem.hrsize, rem.ident))


    def do_dst(self, arg: str) -> None:
        """Sélectionne ou affiche la destination sélectionnée.
        """

        arg_list = arg.split()
        if len(arg_list) > 1:
            self.stdout.write("La commnande n'accepte qu'un argument.\n")
            return

        path_list = [dev.path for dev in lsblk_list()]

        if len(arg) and arg not in path_list:
            self.stdout.write("La cible de la copie doit être le chemin (ex: /dev/sdb) d'un support amovible connecté.\nFaire \"devices\" pour afficher une liste.\n")

        else:
            self._device = arg

        self._print_param("_device")


    def help_dst(self) -> str:
        """Aide longue de do_dst
        """
        help_txt =  "Sélectionne ou affiche la destination sélectionnée.\n\nUsage: dst CHEMIN\n\n   CHEMIN est le chemin du support sur lequel le contenu du répertoire doit être copié.\n  Si aucun argument n'est donné, la destination actuellement sélectionnée est affichée.\n"

        return help_txt


    def do_src(self, arg: str) -> None:
        """Sélectionne ou affiche la source sélectionnée.
        """
        abs_path = ""
        splitted = shlex.split(arg)

        if len(splitted) > 1:
            self.stdout.write("La commnande n'accepte qu'un argument.\n")
            return

        if len(splitted) == 1:
            abs_path = os.path.abspath(splitted[0])

            if os.path.isdir(abs_path):
                self._dirpath = abs_path
            else:
                self.stdout.write("La source doit être un répertoire.\n")
                return

        self._print_param("_dirpath")


    def help_src(self) -> str:
        """Aide longue de do_src
        """
        help_txt = "Sélectionne ou affiche la source sélectionnée.\n\nUsage: src CHEMIN\n\n  CHEMIN est le chemin du répertoire à copier.\n  Si aucun argument n'est donné, la source actuellement sélectionnée est affichée.\n"

        return help_txt


    def do_frmt(self, arg: str) -> None:
        """Bascule l'option de formatage du support de vrai à faux et inversément.
        """
        self._format = not(self._format)
        option = "Oui" if self._format else "Non"

        self.stdout.write("Formater le support: {}\n".format(option))


    def do_fstype(self, arg: str) -> None:
        """Sélectionne ou affiche le type de système de fichier utilisé pour formater le support.
        """
        fstypes = ["ext2", "ext3", "ext4"]

        if not arg in fstypes:
            self.stdout.write("Le système de fichier doit être de l'un des types suivants: {}\n".format(" ".join(fstypes)))
            return

        self._fstype = arg
        self._print_param("_fstype")


    def _get_params(self) -> str:
        _format = "Oui" if self._format else "Non"

        params_txt = """Paramètres actuels de la copie:\n  Source: {source}\n  Destination: {destination}\n  Formater le support: {formater}\n  Système de fichier: {fstype}\n""".format(source=self._dirpath, destination=self._device, formater=_format, fstype=self._fstype)

        return params_txt


    def do_params(self, arg: str) -> None:
        """Affiche les paramètres de la copie.
        """
        self.stdout.write(self._get_params())


    def do_copy(self, arg: str) -> None:
        """Réalise l'opération de copie avec les paramètres choisis.
        """
        params_ok = True

        if not self._dirpath:
            self.stdout.write("Aucun répertoire sélectionné. Utilisez \"dst CHEMIN\"\n")
            params_ok = False

        if not self._device:
            self.stdout.write("Aucun support sélectionné. Utilisez \"src  CHEMIN\". Entrer \"devices\" pour afficher une liste des supports connectés.\n")
            params_ok = False

        if params_ok:
            self.stdout.write(self._get_params())
            res = input("\nT'es sûr de vouloir faire ça? [o/N] ")

            if res in ["o", "O", "y", "Y"]:
                self.stdout.write("Allons-y alors! Démarrage de la copie...\n")
                self.stdout.write("Copie effectuée sans encombre!\n")
            else:
                self.stdout.write("Abandon.\n")

    def help_copy(self) -> str:
        help_txt = "Réalise l'opération de copie avec les paramètres choisis. Les paramètres sont affichés et une confirmation est demandée.\n"

        return help_txt

    def do_quit(self, arg: str) -> bool:
        """Quitte l'application.
        """
        return True


    def _print_param(self, arg_name: str) -> None:
        """Affiche la valeur d'un argument.
        """
        argument = getattr(self, arg_name)

        if not(argument):
            print("Rien de sélectionné encore.")
        else:
            print(argument)


    def do_howto(self, arg: str) -> None:
        """Explication détaillée de la manière de procéder pour réaliser la copie.
        """
        self.stdout.write("En cours...\n")


    def do_help(self, arg: str) -> None:
        """Liste les commandes disponibles. "help <commande>" affiche l'aide pour <commande>.
        """
        if arg:
            sys.stdout.write(self._get_cmd_help(arg))
        else:
            sys.stdout.write(self._get_help())


    def _get_cmd_help(self, arg:str) -> str:
        """Retourne l'aide sur une commande
        """
        try:
            help = getattr(self, 'help_' + arg)
        except AttributeError:
            try:
                doc = getattr(self, 'do_' + arg).__doc__.strip()
                if doc:
                    return "{}\n".format(doc)

            except AttributeError:
                return "Pas d'aide pour {}\n".format(arg)

        return help()


    def _get_help(self) -> str:
        """Retourne l'aide générale.
        """
        cmds_list = list()

        names = [m for m in self.__class__.__dict__.keys() if m.startswith("do_")]
        names.sort()

        for name in names:
            cmd = name[3:]
            cmds_list.append((cmd, getattr(self, name).__doc__.strip()))

        help_txt = "Commandes:\n"

        for cmd, doc in cmds_list:
            spaces = "           "[len(cmd):]
            help_txt += "    {cmd}{spaces}{doc}\n".format(cmd=cmd, spaces=spaces, doc=doc)

        return help_txt


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cli()
    else:
        test = Wcp()
        test.cmdloop()
