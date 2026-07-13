export OPENBLAS_NUM_THREADS=1
mkdir training_data

SETTINGS_FILE=waveform_dataset_settings_two_images_BBH.yaml
OUT_FILE=training_data/waveform_dataset_xphm.hdf5

dingo_lensing_generate_dataset \
  --settings_file "${SETTINGS_FILE}" \
  --out_file "${OUT_FILE}"
