#!/usr/bin/env python
import os
import nipype.pipeline.engine as pe
import nipype.interfaces.io as nio
import argparse
from nipype.interfaces.utility import Function, IdentityInterface
from nipype.interfaces.freesurfer import ReconAll, MRIsCombine, MRIsConvert


def get_niftis(subject_id, data_dir):
    """
    DataGrabber function from 
    https://miykael.github.io/nipype_tutorial/notebooks/basic_data_input_bids.html
    """
    from bids.layout import BIDSLayout
    
    layout = BIDSLayout(data_dir)
    t1s = [f.path for f in layout.get(subject=subject_id, suffix='T1w', run='01',
                                          extension=['nii', 'nii.gz'])]
    delimiter = ', '  # You can choose any delimiter you want

    # Use the join() method to convert the list to a string
    t1 = delimiter.join(t1s)
    return t1

def get_rh(pial_list):
    """
    Is there a better way of doing this?
    """
    for p in pial_list:
        if p.endswith('rh.pial'):
            return p

def get_lh(pial_list):
  """
  Is there a better way of doing this?
  """
  for p in pial_list:
      if p.endswith('lh.pial'):
          return p

def to_list(f1, f2):
    """
    Simple function to format inputs to MRIsCombine
    """
    return [f1, f2]

def main(dataset, output_dir, sub_ids, work_dir):
    """
    Workflow to create stl file(s) for subject from BIDS dataset.
    """
    wf = pe.Workflow('3dbrain')
    wf.base_dir = work_dir  #Set the working directory somewhere on /scratch/nbc/
    wf.config['execution']['crashdump_dir'] = work_dir
    wf.config['execution']['crashfile_format'] = 'txt'
    
    # Enter subjects into workflow
    subj_iterable = pe.Node(IdentityInterface(fields=['subject_id'],
                                              mandatory_inputs=True),
                            name='subj_iterable')
    subj_iterable.iterables = [('subject_id', sub_ids)]
    
    # Grab T1w files from BIDS dataset
    BIDSDataGrabber = pe.MapNode(Function(function=get_niftis,
                                          input_names=['subject_id', 'data_dir'],
                                          output_names=['T1_files']),
                                 iterfield=['subject_id'],
                                 name='BIDSDataGrabber')
    BIDSDataGrabber.inputs.data_dir = dataset
    
    wf.connect(subj_iterable, 'subject_id', BIDSDataGrabber, 'subject_id')
    
    # Perform reconall on T1w files
    reconall = pe.Node(ReconAll(directive='all', openmp=4),
                       name='reconall')
    reconall.inputs.subjects_dir = output_dir  # Should this be the working directory?
    
    wf.connect(subj_iterable, 'subject_id', reconall, 'subject_id')
    wf.connect(BIDSDataGrabber, 'T1_files', reconall, 'T1_files')
    
    # Grab each specific ".pial" file 
    pial_grabber_lh = pe.Node(Function(function=get_lh,
                                       input_names=['pial_list'],
                                       output_names=['lh_pial']),
                                name='pial_grabber_lh')
    wf.connect(reconall, 'pial', pial_grabber_lh, 'pial_list')

    pial_grabber_rh = pe.Node(Function(function=get_rh,
                                       input_names=['pial_list'],
                                       output_names=['rh_pial']),
                                name='pial_grabber_rh')
    wf.connect(reconall, 'pial', pial_grabber_rh, 'pial_list')

    # Convert each ".pial" file to ".stl" format.
    conv_lh = pe.Node(MRIsConvert(out_datatype='stl'), name='conv_lh')
    wf.connect(pial_grabber_lh, 'lh_pial', conv_lh, 'in_file')

    conv_rh = pe.Node(MRIsConvert(out_datatype='stl'), name='conv_rh')
    wf.connect(pial_grabber_rh, 'rh_pial', conv_rh, 'in_file')
    
    # Combine the two GM surface files into a brain.
    # I assume we want to add something to allow users to combine other labels.
    tolist = pe.Node(Function(function=to_list,
                               input_names=['f1', 'f2'],
                               output_names=['lst']),
                       name='ToList')
    wf.connect(conv_lh, 'converted', tolist, 'f1')
    wf.connect(conv_rh, 'converted', tolist, 'f2')
    
    for sub_id in sub_ids:
        out_file_template = os.path.join(output_dir, sub_id, 'surf', f'sub-{sub_id}_combined.stl')
    # Combine the two GM surface files into a brain.
    comb = pe.Node(MRIsCombine(out_file=out_file_template), name='comb')
    wf.connect(tolist, 'lst', comb, 'in_files')
    
    # Save the relevant data into an output directory
    datasink = pe.Node(nio.DataSink(), name='datasink')
    datasink.inputs.base_directory = output_dir
    wf.connect(conv_rh, 'converted', datasink, 'rh_stl')
    wf.connect(conv_lh, 'converted', datasink, 'lh_stl')
    wf.connect(BIDSDataGrabber, 'T1_files', datasink, 'T1s')
    wf.connect(comb, 'out_file', datasink, 'full_stl')
    
    # Run things
    # wf.run(plugin='SLURM', plugin_args={'sbatch_args': '-q pq_nbc'})
    wf.run(plugin='MultiProc', plugin_args={'n_procs': 2, 'overwrite': True})

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Workflow to create stl file(s) for subject from BIDS dataset.')
    parser.add_argument('--dataset', required=True, help='Path to the BIDS dataset directory')
    parser.add_argument('--output_dir', required=True, help='Path to the output directory')
    parser.add_argument('--sub_ids', nargs='+', required=True, help='List of subject IDs')
    parser.add_argument('--work_dir', required=True, help='Path to the working directory')


    args = parser.parse_args()
    main(args.dataset, args.output_dir, args.sub_ids, args.work_dir)