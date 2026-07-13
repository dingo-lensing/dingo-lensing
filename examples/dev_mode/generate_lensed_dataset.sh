#export OPENBLAS_NUM_THREADS=1
# create training_data
#python generate_dataset.py --settings_file waveform_dataset_settings.yaml --out_file training_data/waveform_datasethdf5
dingo_lensing_generate_dataset --settings_file waveform_dataset_settings.yaml --out_file training_data/waveform_dataset.hdf5


