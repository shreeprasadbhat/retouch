from custom_networks import retouch_dual_net
from custom_nuts import ImagePatchesByMaskRetouch
from nutsflow import *
from nutsml import *
import platform
import numpy as np
from custom_networks import retouch_dual_net

if platform.system() == 'Linux':
    DATA_ROOT = '/home/truwan/DATA/retouch/pre_processed/'
else:
    DATA_ROOT = '/Users/ruwant/DATA/retouch/pre_processed/'

BATCH_SIZE = 64


def train_model():
    SplitRandom

    # reading training data
    train_file = DATA_ROOT + 'slice_gt.csv'
    data = ReadPandas(train_file, dropnan=True)
    data = data >> Shuffle(4000) >> Collect()

    # Split the data set into train and test sets with all the slices from the same volume remaining in one split
    same_image = lambda s: s[0]
    train_data, val_data = data >> SplitRandom(ratio=0.75, constraint=same_image)

    def rearange_cols(sample):
        """
        Re-arrange the incoming data stream to desired outputs
        :param sample: 
        :return: 
        """
        img = sample[1] + '_' + sample[0] + '_' + str(sample[3]).zfill(3) + '.tiff'
        mask = sample[1] + '_' + sample[0] + '_' + str(sample[3]).zfill(3) + '.tiff'
        IRF_label = sample[4]
        SRF_label = sample[5]
        PED_label = sample[6]

        return (img, mask, IRF_label, SRF_label, PED_label)

    # training image augementation (flip-lr and rotate)
    # TODO : test adding a contrast enhancement to image
    augment_1 = (AugmentImage((0, 1))
                 .by('identical', 1.0)
                 .by('fliplr', 0.5))

    augment_2 = (AugmentImage((0, 1))
                 .by('identical', 1.0)
                 .by('rotate', 0.5, [0, 10]))

    # augment_3 = (AugmentImage((0))
    #             .by('contrast', 1.0, [0.7, 1.3]))


    # setting up image ad mask readers
    imagepath = DATA_ROOT + 'oct_imgs/*'
    maskpath = DATA_ROOT + 'oct_masks/*'
    img_reader = ReadImage(0, imagepath)
    mask_reader = ReadImage(1, maskpath)

    # randomly sample image patches from the interesting region (based on entropy)
    image_patcher = ImagePatchesByMaskRetouch(imagecol=0, maskcol=1, IRFcol=2, SRFcol=3, PEDcol=4, pshape=(224, 224),
                                              npos=20, nneg=2, pos=1)

    viewer = ViewImage(imgcols=(0, 1), layout=(1, 2), pause=1)

    # building image batches
    build_batch_train = (BuildBatch(BATCH_SIZE, prefetch=0)
                         .by(0, 'image', 'float32', channelfirst=False)
                         .by(1, 'one_hot', 'uint8', 4)
                         .by(2, 'one_hot', 'uint8', 2)
                         .by(3, 'one_hot', 'uint8', 2)
                         .by(4, 'one_hot', 'uint8', 2))

    is_cirrus = lambda v: v[1] == 'Cirrus'

    # TODO : Should I drop non-pathelogical slices
    # Filter to drop all non-pathology patches
    no_pathology = lambda s: (s[2] == 0) and (s[3] == 0) and (s[4] == 0)

    def drop_patch(sample, drop_prob=0.9):
        """
        Randomly drop a patch from iterator if there is no pathology
        :param sample: 
        :param drop_prob: 
        :return: 
        """
        if (sample[2] == 0) and (sample[3] == 0) and (sample[4] == 0):
            return float(np.random.random_sample(1)) < drop_prob
        else:
            return False

    # define the model
    model = retouch_dual_net(input_shape=(224, 224, 1))

    def train_batch(sample):
        model.train_on_batch(sample[0], [sample[2], sample[3], sample[4], sample[1]])

    train_data >> NOP(Filter(is_cirrus)) >> Map(
        rearange_cols) >> img_reader >> mask_reader >> augment_1 >> augment_2 >> Shuffle(
        1000) >> image_patcher >> FilterFalse(drop_patch) >> viewer >> NOP(build_batch_train) >> NOP(
        PrintColType()) >> NOP(Map(train_batch)) >> Consume()

    # # testing one-hot for segmentation
    # build_batch_train = (BuildBatch(1, prefetch=0)
    #                      .by(1, 'one_hot', 'uint8', 4))
    # def reformat(sample):
    #     img = sample[0][0,:,:,0]*255
    #     return (img, )
    # viewer = ViewImage(imgcols=(0), pause=.1)
    # data >> Map(rearange_cols) >> img_reader >> mask_reader >> build_batch_train >> Map(reformat) >> viewer >> PrintColType() >> Consume()


if __name__ == "__main__":
    train_model()
