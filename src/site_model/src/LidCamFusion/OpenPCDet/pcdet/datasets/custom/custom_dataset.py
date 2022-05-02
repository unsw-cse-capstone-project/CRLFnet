from cProfile import label
import copy
import pickle
import os

import numpy as np
from skimage import io

from . import custom_utils
from ...ops.roiaware_pool3d import roiaware_pool3d_utils
from ...utils import box_utils, calibration_kitti, common_utils, object3d_kitti
from ..dataset import DatasetTemplate

class CustomDataset(DatasetTemplate):
    def __init__(self, dataset_cfg, class_names, training=True, root_path=None, logger=None, ext='.bin'):
        """
        Args:
            root_path:
            dataset_cfg:
            class_names:
            training:
            logger:
        """
        super().__init__(
            dataset_cfg=dataset_cfg, class_names=class_names, training=training, root_path=root_path, logger=logger
        )
        self.split = self.dataset_cfg.DATA_SPLIT[self.mode]
        self.root_split_path = os.path.join(
            self.root_path, ('training' if self.split != 'test' else 'testing'))

        split_dir = os.path.join(self.root_path, 'ImageSets',(self.split + '.txt'))
        print("split_dir:",split_dir)
        self.sample_id_list = [x.strip() for x in open(split_dir).readlines()] if os.path.exists(split_dir) else None

        self.custom_infos = []
        self.include_custom_data(self.mode)
        print("****************************custom_infos*************************")
        print(self.custom_infos)
        self.ext = ext

                
    def __len__(self):
        if self._merge_all_iters_to_one_epoch:
            return len(self.sample_id_list) * self.total_epochs

        return len(self.custom_infos)
        
    def __getitem__(self, index):
        if self._merge_all_iters_to_one_epoch:
            index = index % len(self.custom_infos)
        
        info = copy.deepcopy(self.custom_infos[index])

        sample_idx = info['point_cloud']['lidar_idx']



        """
        Function:
            Read 'velodyne' folder as pointclouds
            Read 'label_2' folder as labels
            Return type 'dict'
        """
        lidar_file = os.path.join(self.root_split_path,
                               'velodyne', (self.sample_id_list[index]+self.ext))
        if self.ext == '.bin':
            points = np.fromfile(lidar_file, dtype=np.float32).reshape(-1, 4)
        elif self.ext == '.npy':
            points = np.load(lidar_file)
        else:
            raise NotImplementedError

        input_dict = {
            'points': points,
            'frame_id': self.sample_id_list[index],
        }
        # gt_boxes
        # gt = self.create_groundtruth_database(self.sample_id_list[index])
        # if 'annos' in gt:
        #     annos = gt['annos']
        #     annos = common_utils.drop_info_with_name(annos, name='DontCare')
        #     loc, dims, rots = annos['location'], annos['dimensions'], annos['rotation_y']
        #     gt_names = annos['name']
        #     gt_boxes_lidar = annos['gt_boxes_lidar']

        #     input_dict.update({
        #         'gt_names': gt_names,
        #         'gt_boxes': gt_boxes_lidar
        #     })

        data_dict = self.prepare_data(data_dict=input_dict)
        return data_dict

    def include_custom_data(self, mode):
        if self.logger is not None:
            self.logger.info('Loading Custom dataset.')
        custom_infos = []

        for info_path in self.dataset_cfg.INFO_PATH[mode]:
            info_path = self.root_path / info_path
            if not info_path.exists():
                continue
            with open(info_path, 'rb') as f:
                infos = pickle.load(f)
                custom_infos.extend(infos)
        
        self.custom_infos.extend(custom_infos)

        if self.logger is not None:
            self.logger.info('Total samples for CUSTOM dataset: %d' % (len(custom_infos)))

    # def create_groundtruth_database(self, info_path=None, used_classes=None, split='train'):
    #         import torch

    #         database_save_path = Path(self.root_path) / ('gt_database' if split == 'train' else ('gt_database_%s' % split))
    #         db_info_save_path = Path(self.root_path) / ('kitti_dbinfos_%s.pkl' % split)

    #         database_save_path.mkdir(parents=True, exist_ok=True)
    #         all_db_infos = {}

    #         with open(info_path, 'rb') as f:
    #             infos = pickle.load(f)

    #         for k in range(len(infos)):
    #             print('gt_database sample: %d/%d' % (k + 1, len(infos)))
    #             info = infos[k]
    #             sample_idx = info['point_cloud']['lidar_idx']
    #             points = self.get_lidar(sample_idx)
    #             annos = info['annos']
    #             names = annos['name']
    #             difficulty = annos['difficulty']
    #             bbox = annos['bbox']
    #             gt_boxes = annos['gt_boxes_lidar']

    #             num_obj = gt_boxes.shape[0]
    #             point_indices = roiaware_pool3d_utils.points_in_boxes_cpu(
    #                 torch.from_numpy(points[:, 0:3]), torch.from_numpy(gt_boxes)
    #             ).numpy()  # (nboxes, npoints)

    #             for i in range(num_obj):
    #                 filename = '%s_%s_%d.bin' % (sample_idx, names[i], i)
    #                 filepath = database_save_path / filename
    #                 gt_points = points[point_indices[i] > 0]

    #                 gt_points[:, :3] -= gt_boxes[i, :3]
    #                 with open(filepath, 'w') as f:
    #                     gt_points.tofile(f)

    #                 if (used_classes is None) or names[i] in used_classes:
    #                     db_path = str(filepath.relative_to(self.root_path))  # gt_database/xxxxx.bin
    #                     db_info = {'name': names[i], 'path': db_path, 'image_idx': sample_idx, 'gt_idx': i,
    #                             'box3d_lidar': gt_boxes[i], 'num_points_in_gt': gt_points.shape[0],
    #                             'difficulty': difficulty[i], 'bbox': bbox[i], 'score': annos['score'][i]}
    #                     if names[i] in all_db_infos:
    #                         all_db_infos[names[i]].append(db_info)
    #                     else:
    #                         all_db_infos[names[i]] = [db_info]
    #         for k, v in all_db_infos.items():
    #             print('Database %s: %d' % (k, len(v)))

    #         with open(db_info_save_path, 'wb') as f:
    #             pickle.dump(all_db_infos, f)

    def get_infos(self, num_workers=4, has_label=True, count_inside_pts=True, sample_id_list=None):
        import concurrent.futures as futures

        def process_single_scene(sample_idx):
            print('%s sample_idx: %s' % (self.split, sample_idx))
            # define an empty dict
            info = {}
            # pts infos: dimention and inx
            pc_info = {'num_features': 4, 'lidar_idx': sample_idx}
            # add to pts infos
            info['point_cloud'] = pc_info

            # no images neither calibs

            type_to_id = {'Car': 1, 'Pedestrian': 2, 'Cyclist': 3}
            if has_label:
                # read labels to build object list according to idx
                obj_list = self.get_label(sample_idx)
                # build an empty annotations list
                annotations = {}
                # add to annotations ==> refer to 'object3d_kitti' (no truncated,occluded,alpha,bbox)
                annotations['name'] = np.array([obj[0] for obj in obj_list]) # 1-dimension
                annotations['dimensions'] = np.array([[float(obj[10]), float(obj[8]), float(obj[9])] for obj in obj_list]) # lhw(camera) format 2-dimension
                annotations['location'] = np.array([[float(obj[11]), float(obj[12]), float(obj[13])] for obj in obj_list]) # 2-dimension only one so no concatenate
                annotations['rotation_y'] = np.array([float(obj[14]) for obj in obj_list]) # 1-dimension

                num_objects = len([obj[0] for obj in obj_list if obj[0] != 'DontCare'])
                num_gt = len(annotations['name'])
                index = list(range(num_objects)) + [-1] * (num_gt - num_objects)
                annotations['index'] = np.array(index, dtype=np.int32)

                # attention 'rots'
                loc = annotations['location'][:num_objects]
                dims = annotations['dimensions'][:num_objects]
                rots = annotations['rotation_y'][:num_objects] # * (np.pi / 100)
                # build l,w,h directily from obj
                h = np.array([[float(obj[8])] for obj in obj_list])[:num_objects]
                w = np.array([[float(obj[9])] for obj in obj_list])[:num_objects]
                l = np.array([[float(obj[10])] for obj in obj_list])[:num_objects]
                gt_boxes_lidar = np.concatenate([loc, l, w, h, rots[..., np.newaxis]], axis=1) # 2-dimension array
                annotations['gt_boxes_lidar'] = gt_boxes_lidar
                # print(annotations)
                
                # add annotation info
                info['annos'] = annotations
            
            return info
        
        sample_id_list = sample_id_list if sample_id_list is not None else self.sample_id_list
        # create a thread pool to improve the velocity
        with futures.ThreadPoolExecutor(num_workers) as executor:
            infos = executor.map(process_single_scene, sample_id_list)
        # infos is a list that each element represents per frame
        return list(infos)
                

    def get_label(self, idx):
        # get labels
        label_file = self.root_split_path / 'label_2' / ('%s.txt' % idx)
        # 'object3d.kitti.get_objects_from_label'
        assert label_file.exists()
        objects = []
        with open(label_file, 'r') as f:
            for i in f.readlines():
                cur_object = i.strip('\n').split(' ')
                objects.append(cur_object)
        return objects

    def get_lidar(self, idx):
        """
            Loads point clouds for a sample
                Args:
                    index (int): Index of the point cloud file to get.
                Returns:
                    np.array(N, 4): point cloud.
        """
        # get lidar statistics
        lidar_file = self.root_split_path / 'velodyne' / ('%s.bin' % idx)
        assert lidar_file.exists()
        return np.fromfile(str(lidar_file), dtype=np.float32).reshape(-1, 4)

    def set_split(self, split):
        super().__init__(
            dataset_cfg=self.dataset_cfg, class_names=self.class_names, training=self.training, root_path=self.root_path, logger=self.logger
        )
        self.split = split
        self.root_split_path = self.root_path / ('training' if self.split != 'test' else 'testing')

        split_dir = self.root_path / 'ImageSets' / (self.split + '.txt')
        self.sample_id_list = [x.strip() for x in open(split_dir).readlines()] if split_dir.exists() else None

def create_custom_infos(dataset_cfg, class_names, data_path, save_path, workers=4):
    dataset = CustomDataset(dataset_cfg=dataset_cfg, class_names=class_names, root_path=data_path, training=False)
    train_split, val_split = 'train', 'val'

    train_filename = save_path / ('custom_infos_%s.pkl' % train_split)
    val_filenmae = save_path / ('custom_infos%s.pkl' % val_split)
    trainval_filename = save_path / 'custom_infos_trainval.pkl'
    test_filename = save_path / 'custom_infos_test.pkl'

    print('------------------------Start to generate data infos------------------------')

    dataset.set_split(train_split)
    custom_infos_train = dataset.get_infos(num_workers=workers, has_label=True, count_inside_pts=True)
    with open(train_filename, 'wb') as f:
        pickle.dump(custom_infos_train, f)
    print('Custom info train file is save to %s' % train_filename)

    dataset.set_split('test')
    custom_infos_test = dataset.get_infos(num_workers=workers, has_label=False, count_inside_pts=False)
    with open(test_filename, 'wb') as f:
        pickle.dump(custom_infos_test, f)
    print('Custom info test file is saved to %s' % test_filename)

    print('------------------------Start create groundtruth database for data augmentation------------------------')
    dataset.set_split(train_split)
    print('------------------------Data preparation done------------------------')

if __name__=='__main__':
    import sys
    if sys.argv.__len__() > 1 and sys.argv[1] == 'create_custom_infos':
        import yaml
        from pathlib import Path
        from easydict import EasyDict
        dataset_cfg = EasyDict(yaml.safe_load(open(sys.argv[2])))
        ROOT_DIR = (Path(__file__).resolve().parent / '../../../').resolve()
        create_custom_infos(
            dataset_cfg=dataset_cfg,
            class_names=['Car', 'Pedestrian', 'Cyclist'],
            data_path=ROOT_DIR / 'data' / 'custom',
            save_path=ROOT_DIR / 'data' / 'custom'
        )
