#!/usr/bin/env python
# coding: utf8
#
# Copyright (c) 2020 Centre National d'Etudes Spatiales (CNES).
#
# This file is part of PANDORA
#
#     https://github.com/CNES/Pandora_pandora
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""
This module contains functions associated to the cost volume measure step.
"""

import logging
import numpy as np
import xarray as xr
from math import ceil, floor
from abc import ABCMeta, abstractmethod
from scipy.ndimage.morphology import binary_dilation
from typing import Tuple, Dict, List, Union
from pandora.img_tools import shift_right_img
from json_checker import Or
import rasterio

from pandora.img_tools import compute_std_raster


class AbstractStereo(object):
    __metaclass__ = ABCMeta

    stereo_methods_avail = {}

    def __new__(cls, **cfg: Union[str, int]):
        """
        Return the plugin associated with the stereo_method given in the configuration

        :param cfg: configuration {'stereo_method': value}
        :type cfg: dictionary
        """
        if cls is AbstractStereo:
            if type(cfg['stereo_method']) is str:
                try:
                    return super(AbstractStereo, cls).__new__(cls.stereo_methods_avail[cfg['stereo_method']])
                except KeyError:
                    logging.error("No stereo matching method named {} supported".format(cfg['stereo_method']))
                    raise KeyError
            else:
                if type(cfg['stereo_method']) is unicode:
                    # creating a plugin from registered short name given as unicode (py2 & 3 compatibility)
                    try:
                        return super(AbstractStereo, cls).__new__(
                            cls.stereo_methods_avail[cfg['stereo_method'].encode('utf-8')])
                    except KeyError:
                        logging.error("No stereo matching method named {} supported".format(cfg['stereo_method']))
                        raise KeyError
        else:
            return super(AbstractStereo, cls).__new__(cls)

    @classmethod
    def register_subclass(cls, short_name: str, *args):
        """
        Allows to register the subclass with its short name

        :param short_name: the subclass to be registered
        :type short_name: string
        :param args: allows to register one plugin that contains different methods
        """

        def decorator(subclass):
            cls.stereo_methods_avail[short_name] = subclass
            for arg in args:
                cls.stereo_methods_avail[arg] = subclass
            return subclass

        return decorator

    @abstractmethod
    def desc(self):
        """
        Describes the stereo method
        """
        print('Stereo matching description')

    @abstractmethod
    def compute_cost_volume(self, img_left: xr.Dataset, img_right: xr.Dataset, disp_min: int, disp_max: int
                            ) -> xr.Dataset:
        """
        Computes the cost volume for a pair of images

        :param img_left: left Dataset image
        :type img_left:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param img_right: right Dataset image
        :type img_right:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param disp_min: minimum disparity
        :type disp_min: int
        :param disp_max: maximum disparity
        :type disp_max: int
        :return: the cost volume dataset
        :rtype:
            xarray.Dataset, with the data variables:
                - cost_volume 3D xarray.DataArray (row, col, disp)
                - confidence_measure 3D xarray.DataArray (row, col, indicator)
        """

    def allocate_costvolume(self, img_left: xr.Dataset, subpix: int, disp_min: int, disp_max: int, window_size: int,
                            metadata: dict, np_data: np.ndarray = None) -> xr.Dataset:
        """
        Allocate the cost volume

        :param img_left: left Dataset image
        :type img_left:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param subpix: subpixel precision = (1 or 2 or 4)
        :type subpix: int
        :param disp_min: minimum disparity
        :type disp_min: int
        :param disp_max: maximum disparity
        :type disp_max: int
        :param window_size: size of the aggregation window
        :type window_size: int, odd number
        :param metadata: dictionary storing arbitrary metadata
        :type metadata: dictionary
        :param np_data: the array’s data
        :type np_data: 3D numpy array, dtype=np.float32
        :return: the dataset cost volume with the cost_volume and the confidence measure
        :rtype:
            xarray.Dataset, with the data variables:
                - cost_volume 3D xarray.DataArray (row, col, disp)
                - confidence_measure 3D xarray.DataArray (row, col, indicator)
        """
        c_row = img_left['im'].coords['row']
        c_col = img_left['im'].coords['col']

        # First pixel in the image that is fully computable (aggregation windows are complete)
        offset_row_col = int((window_size - 1) / 2)
        row = np.arange(c_row[0] + offset_row_col, c_row[-1] - offset_row_col + 1)
        col = np.arange(c_col[0] + offset_row_col, c_col[-1] - offset_row_col + 1)

        # Compute the disparity range
        if subpix == 1:
            disparity_range = np.arange(disp_min, disp_max + 1)
        else:
            disparity_range = np.arange(disp_min, disp_max, step=1 / float(subpix))
            disparity_range = np.append(disparity_range, [disp_max])

        # Create the cost volume
        if np_data is None:
            np_data = np.zeros((len(row), len(col), len(disparity_range)), dtype=np.float32)

        cost_volume = xr.Dataset({'cost_volume': (['row', 'col', 'disp'], np_data)},
                                 coords={'row': row, 'col': col, 'disp': disparity_range})
        cost_volume.attrs = metadata

        # Allocate the confidence measure in the cost volume Dataset
        confidence_measure = compute_std_raster(img_left, window_size).reshape(len(row), len(col), 1)
        cost_volume = cost_volume.assign_coords(indicator=['stereo_pandora_intensityStd'])
        cost_volume['confidence_measure'] = xr.DataArray(data=confidence_measure.astype(np.float32),
                                                         dims=['row', 'col', 'indicator'])

        return cost_volume

    def point_interval(self, img_left: xr.Dataset, img_right: xr.Dataset, disp: float) -> \
            Tuple[Tuple[int, int], Tuple[int, int]]:
        """
        Computes the range of points over which the similarity measure will be applied

        :param img_left: left Dataset image
        :type img_left:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param img_right: right Dataset image
        :type img_right:
             xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param disp: current disparity
        :type disp: float
        :return: the range of the left and right image over which the similarity measure will be applied
        :rtype: tuple
        """
        _, nx_left = img_left['im'].shape
        _, nx_right = img_right['im'].shape

        # range in the left image
        p = (max(0 - disp, 0), min(nx_left - disp, nx_left))
        # range in the right image
        q = (max(0 + disp, 0), min(nx_right + disp, nx_right))

        # Because the disparity can be floating
        if disp < 0:
            p = (int(ceil(p[0])), int(ceil(p[1])))
            q = (int(ceil(q[0])), int(ceil(q[1])))
        else:
            p = (int(floor(p[0])), int(floor(p[1])))
            q = (int(floor(q[0])), int(floor(q[1])))

        return p, q

    def masks_dilatation(self, img_left: xr.Dataset, img_right: xr.Dataset, offset_row_col: int, window_size: int,
                         subp: int) -> Tuple[xr.DataArray, List[xr.DataArray]]:
        """
        Return the left and right mask with the convention :
            - Invalid pixels are nan
            - No_data pixels are nan
            - Valid pixels are 0

        Apply dilation on no_data : if a pixel contains a no_data in its aggregation window, then the central pixel
        becomes no_data

        :param img_left: left Dataset image
        :type img_left:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param img_right: right Dataset image
        :type img_right:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param offset_row_col: offset
        :type offset_row_col: int
        :param window_size: window size of the measure
        :type window_size: int
        :param subp: subpixel precision = (1 or 2 or 4)
        :type subp: int
        :param cfg: images configuration containing the mask convention : valid_pixels, no_data
        :type cfg: dict
        :return: the left mask and the right masks
        :rtype:
            tuple (left mask, list[right mask, right mask shifted by 0.5])
                - left mask :  xarray.DataArray msk 2D(row, col)
                - right mask :  xarray.DataArray msk 2D(row, col)
                - right mask shifted :  xarray.DataArray msk 2D(row, shifted col by 0.5)
        """
        # Create the left mask with the convention : 0 = valid, nan = invalid and no_data
        if 'msk' in img_left.data_vars:
            dilatate_left_mask = np.zeros(img_left['msk'].shape)
            # Invalid pixels are nan
            dilatate_left_mask[
                np.where((img_left['msk'].data != img_left.attrs['valid_pixels']) & (
                            img_left['msk'].data != img_left.attrs['no_data_mask']))] = np.nan
            # Dilatation : pixels that contains no_data in their aggregation window become no_data = nan
            dil = binary_dilation(img_left['msk'].data == img_left.attrs['no_data_mask'],
                                  structure=np.ones((window_size, window_size)), iterations=1)
            dilatate_left_mask[dil] = np.nan
        else:
            # All pixels are valid
            dilatate_left_mask = np.zeros(img_left['im'].shape)

        # Create the right mask with the convention : 0 = valid, nan = invalid and no_datassssss
        if 'msk' in img_right.data_vars:
            dilatate_right_mask = np.zeros(img_right['msk'].shape)
            # Invalid pixels are nan
            dilatate_right_mask[
                np.where((img_right['msk'].data != img_right.attrs['valid_pixels']) & (
                            img_right['msk'].data != img_right.attrs['no_data_mask']))] = np.nan
            # Dilatation : pixels that contains no_data in their aggregation window become no_data = nan
            dil = binary_dilation(img_right['msk'].data == img_right.attrs['no_data_mask'],
                                  structure=np.ones((window_size, window_size)), iterations=1)
            dilatate_right_mask[dil] = np.nan

        else:
            # All pixels are valid
            dilatate_right_mask = np.zeros(img_left['im'].shape)

        if offset_row_col != 0:
            # Truncate the masks to the size of the cost volume
            dilatate_left_mask = dilatate_left_mask[offset_row_col:-offset_row_col, offset_row_col:-offset_row_col]
            dilatate_right_mask = dilatate_right_mask[offset_row_col:-offset_row_col, offset_row_col:-offset_row_col]

        ny_, nx_ = img_left['im'].shape
        row = np.arange(0 + offset_row_col, ny_ - offset_row_col)
        col = np.arange(0 + offset_row_col, nx_ - offset_row_col)

        # Shift the right mask, for sub-pixel precision. If an no_data or invalid pixel was used to create the
        # sub-pixel point, then the sub-pixel point is invalidated / no_data.
        dilatate_right_mask_shift = xr.DataArray()
        if subp != 1:
            # Since the interpolation of the right image is of order 1, the shifted right mask corresponds
            # to an aggregation of two columns of the dilated right mask
            str_row, str_col = dilatate_right_mask.strides
            shape_windows = (dilatate_right_mask.shape[0], dilatate_right_mask.shape[1] - 1, 2)
            strides_windows = (str_row, str_col, str_col)
            aggregation_window = np.lib.stride_tricks.as_strided(dilatate_right_mask, shape_windows, strides_windows)
            dilatate_right_mask_shift = np.sum(aggregation_window, 2)

            # Whatever the sub-pixel precision, only one sub-pixel mask is created,
            # since 0.5 shifted mask == 0.25 shifted mask
            col_shift = np.arange(0 + offset_row_col + 0.5, nx_ - 1 - offset_row_col, step=1)
            dilatate_right_mask_shift = xr.DataArray(dilatate_right_mask_shift,
                                                   coords=[row, col_shift], dims=['row', 'col'])

        dilatate_left_mask = xr.DataArray(dilatate_left_mask,
                                         coords=[row, col], dims=['row', 'col'])
        dilatate_right_mask = xr.DataArray(dilatate_right_mask,
                                         coords=[row, col], dims=['row', 'col'])

        return dilatate_left_mask, [dilatate_right_mask, dilatate_right_mask_shift]

    @staticmethod
    def dmin_dmax(disp_min: Union[int, np.ndarray], disp_max: Union[int, np.ndarray]) -> Tuple[int, int]:
        """
        Find the smallest disparity present in disp_min, and the highest disparity present in disp_max

        :param disp_min: minimum disparity
        :type disp_min: int or np.ndarray
        :param disp_max: maximum disparity
        :type disp_max: int or np.ndarray
        :return:
            dmin_min: the smallest disparity in disp_min
            dmax_max: the highest disparity in disp_max
        :rtype: Tuple(int, int)
        """
        # Disp_min is a fixed disparity
        if type(disp_min) == int:
            dmin_min = disp_min

        # Disp_min is a variable disparity
        else:
            dmin_min = int(np.nanmin(disp_min))

        # Disp_max is a fixed disparity
        if type(disp_max) == int:
            dmax_max = disp_max

        # Disp_max is a variable disparity
        else:
            dmax_max = int(np.nanmax(disp_max))

        return dmin_min, dmax_max

    def cv_masked(self, img_left: xr.Dataset, img_right: xr.Dataset, cost_volume: xr.Dataset,
                  disp_min: Union[int, np.ndarray], disp_max: Union[int, np.ndarray]) -> xr.Dataset:
        """
        Masks the cost volume :
            - costs which are not inside their disparity range, are masked with a nan value
            - costs of invalid_pixels (invalidated by the input image mask), are masked with a nan value
            - costs of no_data pixels, are masked with a nan value. If a valid pixel contains a no_data in its
                aggregation window, then the cost of the central pixel is masked with a nan value

        :param img_left: left Dataset image
        :type img_left:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param img_right: right Dataset image
        :type img_right:
            xarray.Dataset containing :
                - im : 2D (row, col) xarray.DataArray
                - msk : 2D (row, col) xarray.DataArray
        :param cost_volume: the cost_volume DataSet
        :type cost_volume:
            xarray.Dataset, with the data variables:
                - cost_volume 3D xarray.DataArray (row, col, disp)
                - confidence_measure 3D xarray.DataArray (row, col, indicator)
        :param disp_min: minimum disparity
        :type disp_min: int or np.ndarray
        :param disp_max: maximum disparity
        :type disp_max: int or np.ndarray
        :param cfg: images configuration containing the mask convention : valid_pixels, no_data
        :type cfg: dict
        :return: the cost_volume DataArray masked
        :rtype: 3D xarray.DataArray (row, col, disp)
        """
        ny_, nx_, nd_ = cost_volume['cost_volume'].shape

        dmin, dmax = self.dmin_dmax(disp_min, disp_max)

        # ----- Masking invalid pixels -----

        # Contains the shifted right images
        img_right_shift = shift_right_img(img_right, self._subpix)

        # Computes the validity mask of the cost volume : invalid pixels or no_data are masked with the value nan.
        # Valid pixels are = 0
        offset = int((self._window_size - 1) / 2)
        mask_left, mask_right = self.masks_dilatation(img_left, img_right, offset, self._window_size, self._subpix)
        offset_mask = (int(self._window_size / 2) * 2)

        for disp in cost_volume.coords['disp'].data:
            i_right = int((disp % 1) * self._subpix)
            p, q = self.point_interval(img_left, img_right_shift[i_right], disp)

            # Point interval in the left image
            p_mask = (p[0], p[1] - offset_mask)
            # Point interval in the right image
            q_mask = (q[0], q[1] - offset_mask)

            i_mask_right = min(1, i_right)
            d = int((disp - dmin) * self._subpix)

            # Invalid costs in the cost volume
            cost_volume['cost_volume'].data[:, p_mask[0]:p_mask[1], d] += (
                    mask_right[i_mask_right].data[:, q_mask[0]:q_mask[1]] + mask_left.data[:, p_mask[0]:p_mask[1]])

        # ----- Masking disparity range -----

        # Fixed range of disparities
        if type(disp_min) == int and type(disp_max) == int:
            return cost_volume

        # Variable range of disparities
        # Resize disparity grids : disparity grids size and cost volume size must be equal
        offset = int(cost_volume.attrs['offset_row_col'])
        if offset == 0:
            disp_min_crop = disp_min
            disp_max_crop = disp_max
        else:
            disp_min_crop = disp_min[offset: -offset, offset: -offset]
            disp_max_crop = disp_max[offset: -offset, offset: -offset]

        # Mask the costs computed with a disparity lower than disp_min and higher than disp_max
        for d in range(nd_):
            masking = np.where(np.logical_or(cost_volume.coords['disp'].data[d] < disp_min_crop,
                                             cost_volume.coords['disp'].data[d] > disp_max_crop))
            cost_volume['cost_volume'].data[masking[0], masking[1], d] = np.nan

        return cost_volume