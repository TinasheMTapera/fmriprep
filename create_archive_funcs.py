import os
import re

#### Define functions

def get_flywheel_hierarchy(fw, container_id, container_type):
    """
        Takes fw client, a container id and container_type as input

        container_id: the ID of the session or project
        container_type: the type of the ID, either 'session' or 'project'

        Returns the flywheel tree

        example:

        {
        "<project_id>": {
           "<session_id>": {
                    "label": "ses11123",
                    "subject_code": "001",
                    "acquisitions": {
                        "<acquisition_id1>": {
                            "label": "T1 MPRAGE",
                            "created": "2017-09-19T14:39:58.721Z",
                            "files": ['T1_dicom.zip', 'T1.nii.gz'],
                            'measurements': ['Anatomy_t1w', None],
                            'type': ['dicom', 'nifti'],
                    },
                        "<acquisition_id2>": {
                            "label": "task123123",
                            "created": "2017-09-19T12:39:58.721Z",
                            "files": ['fmri_dicom.zip', 'fmri.nii.gz'],
                            'measurements': ['Functional', None],
                            'type': ['dicom', 'nifti'],
                    }
                }
            }
        }
    }


    """

    # Determine if ID is a project or a session ID
    if container_type == 'project':
        # Get list of sessions within project
        project_sessions = fw.get_project_sessions(container_id)
        project_id = container_id
    elif container_type == 'session':
        # If container ID is actually a session, get the specific session
        session = fw.get_session(container_id)
        # Place the single session within a list to iterate over (mirrors project_sessions above)
        project_sessions = [session]
        project_id = session.get('project')
    else:
        print("Container ID %s is not associated with a project or a session" % container_id)
        raise Exception

    # Create dictionary to place flywheel hierarchy info
    flywheel_hierarchy = {project_id: {}}
    # Iterate over every session within project
    for p_ses in project_sessions:
        # Get session ID, session label and subject code to place in dictionary
        session_id = p_ses.get('_id')
        # If no subject code present, continue...
        if not ('code' in p_ses['subject'].keys()):
            continue
        flywheel_hierarchy[project_id][session_id] = {'label': p_ses.get('label'),
                                                     'subject_code': p_ses['subject']['code'],
                                                     'acquisitions': {}
                                                     }
        # Get all acquisitions within session
        session_acqs = fw.get_session_acquisitions(session_id)
        # Iterate over all acquisitions within session
        for s_acq in session_acqs:
            # Get acquistiion ID and place in dictionary
            acq_id = s_acq.get('_id')
            flywheel_hierarchy[project_id][session_id]['acquisitions'][acq_id] = {'label': s_acq.get('label'),
                                                                                  'created': s_acq.get('created'),
                                                                                  'files': [],
                                                                                  'measurements': [],
                                                                                  'type': []
            }
            # Iterate over all files within acquisition
            for f in s_acq['files']:
                filename = f['name']
                ## Sometimes measurement is not present - if not, assign measurement value to be None
                if 'measurements' in f.keys():
                    # my BIDS code is assuming that there is a one-to-one relationship between files and measurements
                    # Probably a bad assumption and this should be improved...
                    measurement = f['measurements'][0]
                else:
                    measurement = None
                # Get type - we are only concerned with nifti and source code files
                #   NIfTI because that's what BIDS requires
                #   source code because we need sidecar JSON files
                # Determine file type
                ftype = f.get('type')
                if ftype in ['nifti', 'source code']:
                    flywheel_hierarchy[project_id][session_id]['acquisitions'][acq_id]['files'].append(filename)
                    flywheel_hierarchy[project_id][session_id]['acquisitions'][acq_id]['measurements'].append(measurement)
                    flywheel_hierarchy[project_id][session_id]['acquisitions'][acq_id]['type'].append(ftype)

    return flywheel_hierarchy


def populate_bids_hierarchy(bids_filepath, bids_hierarchy):

    # split up path, participant, session, 'anat'/'func', filename
    participant, session, subdir, filename = bids_filepath.split('/')

    ## Populate bids_hierarchy
    if participant not in bids_hierarchy:
        bids_hierarchy[participant] = {}
    if session not in bids_hierarchy[participant]:
        bids_hierarchy[participant][session] = {}
    if subdir not in bids_hierarchy[participant][session]:
        bids_hierarchy[participant][session][subdir] = []

    bids_hierarchy[participant][session][subdir].append(filename)

    return bids_hierarchy

def make_bids_spec(desc, flywheel_val, label_type):
    """ Asserts if label already conforms to the BIDS spec, if not
    converts the 'flywheel_val' variable into a BIDS allowable string

    desc: string describing the type of label
            ex: sub-
                ses-
                acq-
                ce-
                task-
    flywheel_val: the value of the Flywheel string such as the subject code
            ex: amyg_s11_ses2_pcolA
                session4
                s004

    valtype: the label type, is either 'label' or 'index'
            label indicates only alphanumeric values are allowed
            index indicates only numeric values are allowed

    returns: the label within BIDS format
            ex: sub-control001
                ses-123
                acq-t1w

    """
    # If BIDS 'label', then any letter and number is allowed
    if label_type == 'label':
        # Define regex to check for BIDS compliance
        regex = '[0-9a-zA-Z]+$'
        # Extract BIDS compliant values, incase the flywheel_val is NOT BIDS
        extract_values = ''.join(ch for ch in flywheel_val if ch.isalnum())
    # if BIDS 'index', then any number is allowed
    if label_type == 'index':
        # Define regex to check for BIDS compliance
        regex = '[0-9]+$'
        # Extract BIDS compliant values, incase the flywheel_val is NOT BIDS
        extract_values = re.sub(r'\D+', '', flywheel_val)
    # Check if flywheel value already conforms to bids spec
    pattern = desc + regex
    already_bids = re.match(pattern, flywheel_val)
    if already_bids:
        label_bids = flywheel_val
    # Otherwise, grab all permissible values from subject_code and make that the participant
    else:
        label_bids = desc + extract_values
    return label_bids


def create_bids_hierarchy(fw, flywheel_hierarchy, test_bool=False):
    """
    """

    # Keep track of what file within the Flywheel hierarchy goes with what file within BIDS hierarchy
    #    list of paired lists [['/flywheel/hierarchy/file.nii', '/bids/hierarchy/file.nii'], ... ]
    files_lookup = []
    ## Traverse over Flywheel hierarchy to generate BIDS hierarchy
    bids_hierarchy_tmp = {}
    # Participant Directory
    for project in flywheel_hierarchy.keys():
        # Session Directory
        for session_id in flywheel_hierarchy[project].keys():
            # Check for acquisitions
            if not ('acquisitions' in flywheel_hierarchy[project][session_id].keys()):
                continue
            # Iterate over acquisitions
            for acq_id in flywheel_hierarchy[project][session_id]['acquisitions'].keys():
                # If there isn't a nifti file in the acquisition, move on!!
                if not ('nifti' in flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['type']):
                    print ("No nifti files within acquisition, moving on...")
                    continue

                # Get meta info for BIDS
                subject_code = flywheel_hierarchy[project][session_id]['subject_code']
                session_label = flywheel_hierarchy[project][session_id]['label']
                measurements = flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['measurements']

                # Get nifti file
                # NOTE! If there are multiple nifti files within the one acquisition, this will take the last one in
                #         the list, under the assumption that it is the most recent
                reversed_typelist = flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['type'][::-1]
                nifti_idx = reversed_typelist.index('nifti')
                reversed_filelist = flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['files'][::-1]
                nifti_filename = reversed_filelist[nifti_idx]
                # Define the extension (.nii or .nii.gz)
                if '.nii.gz' in nifti_filename:
                    extension = '.nii.gz'
                if '.nii' in nifti_filename:
                    extension = '.nii'
                else:
                    print(nifti_filename)
                    print('we here')
                    extension = 'NONONONO'

                # Define the path of the desired nifti file within the flywheel hierarchy
                flywheel_filepath = os.path.join(project, session_id, acq_id, nifti_filename)

                ### Making BIDS
                # Generate the participant information (i.e. sub-001)
                participant_bids = make_bids_spec('sub-', subject_code, 'label')
                # Generate the session information (i.e. ses-1234)
                session_bids = make_bids_spec('ses-', session_label, 'label')
                # Get acquistion label
                acquisition_label = flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['label']

                ### HANDLE T1w/T2w images
                if ('anatomy_t1w' in measurements) or ('anatomy_t2w' in measurements):
                    # Define dirname
                    bids_dirname = 'anat'

                    #### Making BIDS
                    # Create the new name of the file that conforms to bids spec
                    if 'anatomy_t1w' in measurements:
                        desc = 'T1w'
                    if 'anatomy_t2w' in measurements:
                        desc = 'T2w'
                    bids_filename = '%s_%s_%s%s' % (participant_bids, session_bids, desc, extension)

                ### HANDLE Functional images
                elif 'functional' in measurements:
                    # Define dirname
                    bids_dirname = 'func'

                    #### Making BIDS
                    # Use the acquistion label as the task name (i.e. task-balloontask or task-rest)
                    # If rest is in the acquisition label, will classify as resting state
                    if 'rest' in acquisition_label.lower():
                        taskname = 'task-rest'
                    # Otherwise, the taskname will take all permitted values from acquisition_label
                    else:
                        taskname = make_bids_spec('task-', acquisition_label, 'label')

                    # check if sbref is in the acquistion label, if so, use sbref as filename description
                    if 'sbref' in acquisition_label.lower():
                        bids_func_desc = 'sbref'
                        # remove sbref from taskname, if present
                        pattern = re.compile(bids_func_desc, re.IGNORECASE)
                        taskname = re.sub(pattern, '', taskname)
                    else:
                        bids_func_desc = 'bold'

                    # Create the new name of the file that conforms to bids spec
                    bids_filename = '%s_%s_%s_%s%s' % (participant_bids, session_bids, taskname, bids_func_desc, extension)

                ### HANDLE Fieldmap images
                elif 'field_map' in measurements:
                    # Define dirname
                    bids_dirname = 'fmap'

                    #### Making BIDS
                    # determine type of fieldmap from acquisition label
                    #
                    # Possible field maps
                    # (1)  phasediff & magnitude (2 images)
                    #   _phasediff & _magnitude1/_magnitude2
                    # (2) 2 phase images & 2 magnitude images
                    #  _phase1/_phase2 & _magnitude1/_magnitude2
                    # (3) single real fieldmap NOTE!!! NOT HANDLING THIS CASE - not sure how!!
                    #  _magnitude & _fieldmap
                    # (4) multiple phase encoded directions
                    #  _dir-<dirlabel>_epi where dirlabel is AP/PA/LR/RL etc...
                    # NOTE: all files above need a sidecar json except for magnitude images
                    acquisition_label_lower = acquisition_label.lower()
                    # (1) If phasediff
                    if 'phasediff' in acquisition_label_lower:
                        bids_field_desc = 'phasediff'
                    # (2) if magnitude
                    elif 'mag' in acquisition_label_lower:
                        bids_field_desc = 'magnitude'
                    # (4) If spin echo
                    if 'spinecho' in acquisition_label_lower:
                        ## Determine dir_label
                        re_match = re.search('AP|PA|LR|RL', acquisition_label)
                        if re_match:
                            dir_label = acquisition_label[re_match.start():re_match.end()]
                        else:
                            dir_label = 'unknown'
                        bids_field_desc = 'dir-%s_epi' % dir_label
                    # Create the new name of the file that conforms to bids spec
                    bids_filename = '%s_%s_%s%s' % (participant_bids, session_bids, bids_field_desc, extension)

                else:
                    continue

                ### TODO: If 'run%d' at the end of the acquisition label -- honor that number and change to BIDS format
                # 'task-foorun1' -> 'task-foo_run-1'
                bids_filename = re.sub(r'(run)(\d)', r'_\1-\2', bids_filename)

                # Now append directory
                # Define the path of the new nifti file within the bids hierarchy
                bids_filepath = os.path.join(participant_bids, session_bids, bids_dirname, bids_filename)
                # Append to file lookup
                files_lookup.append([flywheel_filepath, bids_filepath])
                # Populate bids hierarchy
                populate_bids_hierarchy(bids_filepath, bids_hierarchy_tmp)



    ### Iterate over files looking for duplicates and add run numbers if necessary
    for sub_dir in bids_hierarchy_tmp.keys():
        for ses_dir in bids_hierarchy_tmp[sub_dir].keys():
            for desc_dir in bids_hierarchy_tmp[sub_dir][ses_dir].keys():
                bids_files = bids_hierarchy_tmp[sub_dir][ses_dir][desc_dir]
                # Get a list of duplicate filenames that need to be renamed
                duplicates = [x for x in set(bids_files) if bids_files.count(x) > 1]
                # Identify the corresponding flywheel files that have bids duplicates
                flywheel_files = [item[0] for item in files_lookup \
                                  if os.path.basename(item[1]) in duplicates]
                # Get timing information about the duplicate files in order to assign run-<index>
                created = []
                for ff in flywheel_files:
                    project_id, session_id, acq_id, filename = ff.split('/')
                    # list of tuples [(timestamp, flywheel_filename), ...]
                    created.append(
                                (flywheel_hierarchy[project_id][session_id]['acquisitions'][acq_id]['created'], ff)
                                  )
                # Sort list of files based on timestamp which is first item in tuple
                created.sort(key=lambda x: x[0])
                # Go through the created list and assign the run counts
                for idx in range(len(created)):
                    # Get flywheel filename
                    fff = created[idx][1]
                    # Get corresponding bids filename
                    for idxx in range(len(files_lookup)):
                        if files_lookup[idxx][0] == fff:
                            bbb = files_lookup[idxx][1]
                            break
                    # Now rename bids filename (variable name: 'bbb')
                    #    sub-<label>_ses-<label>_T1w.nii.gz
                    #               =>
                    #        sub-<label>_ses-<label>_run-<index>_T1w.nii.gz
                    #
                    #    sub-<label>_ses-<label>_task-<label>_bold.nii.gz
                    #               =>
                    #        sub-<label>_ses-<label>_task-<label>_run-<index>_bold.nii.gz
                    bbb_new = re.sub(r'(_T1w|_bold|_sbref)', r'_run-%d\1' % (idx+1), bbb)
                    # Update the files_lookup information
                    files_lookup[idxx][1] = bbb_new

    ### Create new bids_hierarchy with all unique filenames
    bids_hierarchy = {}
    for f,b  in files_lookup:
        populate_bids_hierarchy(b, bids_hierarchy)

    ### Create JSON files
    #   FUNCTIONAL IMAGES REQUIRE
    #       RepetitionTime
    #       TaskName
    #   T1W IMAGES OPTIONAL
    for f,b in files_lookup:
        if '_bold.nii' in b:
            # Get meta information to create json file
            project_id, session_id, acq_id, filename = f.split('/')
            if test_bool: meta_info = {'info': {'RepetitionTime': 123}} ## to help with writing test use cases
            else:
                # Need Repetition Time information
                acq_info = fw.get_acquisition(acq_id)
                for f in acq_info['files']:
                    if 'info' in f.keys():
                        if 'RepetitionTime' in f['info'].keys():
                            meta_info = {'RepetitionTime': f['info']['RepetitionTime']}
                            break
                        else:
                            print("Warning: Repetition Time missing for acquisition: %s" % acquisition_id)

            # Place TaskName into the file -- just using Acquisition Label
            #    NOTE: it is not clear within the bids spec if the Task Name can have any character
            #       it seems like there is a distinction between task NAME and task LABEL where
            #       task LABEL has restrictions but task NAME does not...
            # To be safe, I'll make it the TASK LABEL
            #NOT THIS:meta_info['TaskName'] = flywheel_hierarchy[project][session_id]['acquisitions'][acq_id]['label']
            # Pull task label out of bids filename
            find_taskname = re.search('task-[a-zA-Z0-9]+', b)
            meta_info['TaskName'] = b[find_taskname.start()+5:find_taskname.end()]
            # Save meta information to JSON file
            json_filename = re.sub(r'(.nii.gz|.nii)', r'.json', b)
            # Add json_filename to bids_hierarchy
            populate_bids_hierarchy(json_filename, bids_hierarchy)
            # Add JSON blob and JSON filename to files_lookup
            files_lookup.append([meta_info, json_filename])

    return bids_hierarchy, files_lookup
