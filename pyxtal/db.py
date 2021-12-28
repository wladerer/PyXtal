"""
Database class
"""
import os
from ase.db import connect

class database():
    """
    This is a database class to process crystal data

    Args:
        db_name: *.db format from ase database
    """

    def __init__(self, db_name):
        self.db_name = db_name
        if not os.path.exists(db_name):
            raise ValueError(db_name, 'doesnot exist')

        self.db = connect(db_name)
        self.get_all_codes()
        self.keys = ['csd_code', 'space_group', 'spg_num',
                     'Z', 'Zprime', 'url', 'mol_name',
                     'mol_smi', 'mol_formula', 'mol_weight',
                     'l_type',
                    ]
        self.calculators = ['charmm', 
                            'gulp', 
                            'ani',
                            'dftb_D3',
                            'dftb_TS',
                           ]

    def vacuum(self):
        self.db.vacuum()

    def get_all_codes(self):
        codes = []
        for row in self.db.select():
            if row.csd_code not in codes:
                codes.append(row.csd_code)
            else:
                print('find duplicate! remove', row.csd_code)
                self.db.delete(row.id)
        self.codes = codes

    def add(self, entry):
        (atom, kvp, data) = entry
        if kvp['csd_code'] not in self.codes:
            kvp0 = self.process_kvp(kvp)
            self.db.write(atom, key_value_pairs=kvp0, data=data)

    def process_kvp(self, kvp):
        kvp0 = {}
        for key in self.keys:
            if key in kvp:
                kvp0[key] = kvp[key]
            else:
                print('Error, cannot find ', key, ' from the input')
                return 
        return kvp0

    def check_status(self, show=False):
        """
        Check the current status of each entry
        """
        ids = []
        for row in self.db.select():
            if len(row.data.keys())==len(self.calculators):
                ids.append(row.id)        
                if show:
                    row_info = self.get_row_info(id=row.id)
                    self.view(row_info)
            else:
                print(row.csd_code) #, row.data['charmm_info']['prm'])
        return ids

    def copy(self, db_name, csd_codes):
        """
        copy the entries to another db

        Args:
            db_name: db file name
            csd_codes: list of codes
        """
        if db_name == self.db_name:
            raise RuntimeError('Cannot use the same db file for copy')
        with connect(db_name) as db:
            for csd_code in csd_codes:
                row_info = self.get_row_info(code=csd_code)
                (atom, kvp, data) = row_info
                db.write(atom, key_value_pairs=kvp, data=data)

    def view(self, row_info):
        """
        print the summary of benchmark results

        Args:
            row: row object
        """
        from pyxtal import pyxtal
        from pyxtal.util import ase2pymatgen
        from pyxtal.representation import representation
        from pyxtal.msg import ReadSeedError

        (atom, kvp, data) = row_info

        #Reference
        xtal = self.get_pyxtal(kvp['csd_code'])
        rep = xtal.get_1D_representation()
        print('\n', kvp['csd_code'], kvp['mol_smi'], xtal.lattice.volume)
        print(rep.to_string() + ' reference')

        #calcs
        for key in data.keys():
            calc = key[:-5]
            time = data[key]['time'] 

            rep = data[key]['rep']
            if type(rep[0]) is not list: rep = [rep]
            rep = representation(rep, kvp['mol_smi']).to_string()

            (dv, msd1, msd2) = data[key]['diff'] 
            strs = "{:s} {:8s} {:6.2f} {:6.3f}".format(rep, calc, time/60, dv)
            if msd1 is not None:
                strs += "{:6.3f}{:6.3f}".format(msd1, msd2)
            print(strs)


    def get_row_info(self, id=None, code=None):
        match = False
        if id is not None:
            for row in self.db.select(id=id):
                match = True
                break
        elif code is not None:
            for row in self.db.select(csd_code=code):
                match = True
                break
        if match:

            kvp = {}
            for key in self.keys:
                kvp[key] = row.key_value_pairs[key]

            data0 = {}
            for calc in self.calculators:
                key = calc + '_info'
                if key in row.data.keys():
                    data0[key] = row.data[key]

            atom = self.db.get_atoms(id=row.id)
            return (atom, kvp, data0)
        else:
            msg = 'cannot find the entry from ' + id + code
            raise RuntimeError(msg)

    def get_row(self, code):
        for row in self.db.select(csd_code=code):
            return row
        msg = 'cannot find the entry from ' + code
        raise RuntimeError(msg)

    def get_pyxtal(self, code):
        from pyxtal import pyxtal
        from pyxtal.util import ase2pymatgen
        from pyxtal.msg import ReadSeedError

        row = self.get_row(code)
        atom = self.db.get_atoms(id=row.id)
        #Reference
        pmg = ase2pymatgen(atom)
        smi = row.mol_smi
        smiles = smi.split('.')
        molecules = [smile+'.smi' for smile in smiles]

        xtal = pyxtal(molecular=True)
        try:
            xtal.from_seed(pmg, molecules=molecules)
        except ReadSeedError:
            xtal.from_seed(pmg, molecules=molecules, add_H=True)

        return xtal

    def compute(self, row, work_dir, skf_dir):
        if len(row.data.keys())<len(self.calculators):
            #not label information, run antechamber
            atom = self.db.get_atoms(id=row.id)
            if 'gulp_info' not in row.data.keys():
                pmg, c_info, g_info = get_parameters(row, atom)
                row.data = {'charmm_info': c_info,
                            'gulp_info': g_info
                           }
            else:
                pmg = ase2pymatgen(atom)

            data = compute(row, pmg, work_dir, skf_dir)
            self.db.update(row.id, data=data)
            print('updated the data for', row.csd_code)


if __name__ == "__main__":
    # open
    db = database('test.db')
    print("Total number of entries", len(db.codes))

    # view structure
    c = db.get_pyxtal('HXMTAM')
    print(c)
