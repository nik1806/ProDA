# python generate_pseudo_label.py \
#     --name gta2citylabv2_stage1Denoise --flip \
#     --resume_path pretrained/gta2citylabv2_stage1Denoise/gta5_deepv2_trained_dass51.pth \
#     --no_droplast

    # --resume_path logs/gta2citylabv2_stage1Denoise/from_gta5_to_cityscapes_on_deeplabv2_best_model.pkl \

python train.py \
    --name gta2citylabv2_stage2 \
    --stage stage2 \
    --used_save_pseudo --path_LP Pseudo/gta2citylabv2_stage1Denoise \
    --resume_path pretrained/gta2citylabv2_stage1Denoise/gta5_deepv2_trained_dass51.pth \
    --S_pseudo 1 --threshold 0.95 --distillation 1 --finetune --lr 6e-4 --student_init simclr --bn_clr --no_resume

    # --resume_path ./logs/gta2citylabv2_stage1Denoise/from_gta5_to_cityscapes_on_deeplabv2_best_model.pkl \