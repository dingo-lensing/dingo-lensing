#!/bin/bash
SETTING_FILE=train_settings_xphm_prod.yaml
TRAIN_DIR=training

#avoid multi thread error during SVD basis generation
export OPENBLAS_NUM_THREADS=1

#set your gpu
export CUDA_VISIBLE_DEVICES=

dingo train --settings_file "$SETTING_FILE" --train_dir "$TRAIN_DIR"

#resume training
#"$DINGO_TRAIN_BIN" --checkpoint training/model_latest.pt --train_dir "$TRAIN_DIR"

