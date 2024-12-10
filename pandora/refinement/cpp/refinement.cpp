#include <pybind11/functional.h>
#include "includes/refinement.hpp"
#include <algorithm>
#include <numeric>
#include <cmath>
#include <iostream>

namespace py = pybind11;

std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<int64_t>> loop_refinement(
    py::array_t<float> cv,
    py::array_t<float> disp,
    py::array_t<int64_t> mask,
    double d_min,
    double d_max,
    int subpixel,
    std::string measure,
    std::function<
        std::tuple<float, float, int>(py::array_t<float>, float, std::string, int)
    > &method,
    int64_t cst_pandora_msk_pixel_invalid, 
    int64_t cst_pandora_msk_pixel_stopped_interpolation 
) {
    auto r_cv = cv.unchecked<3>();
    auto rw_mask = mask.mutable_unchecked<2>();
    auto rw_disp = disp.mutable_unchecked<2>();
    size_t n_row = r_cv.shape(0);
    size_t n_col = r_cv.shape(1);
    size_t n_disp = r_cv.shape(2);

    py::array_t<float> itp_coeff = py::array_t<float>({n_row, n_col});
    auto rw_itp_coeff = itp_coeff.mutable_unchecked<2>();

    for (size_t row = 0; row < n_row; ++row) {
        for (size_t col = 0; col < n_col; ++col) {
            
            if ((rw_mask(row, col) & cst_pandora_msk_pixel_invalid) != 0) {
                rw_itp_coeff(row, col) = std::numeric_limits<float>::quiet_NaN();
                continue;
            }

            float raw_dsp = rw_disp(row, col);
            int dsp = (int)( (raw_dsp - d_min) * subpixel );
            float dsp_cost = r_cv(row, col, dsp);
            if (std::isnan(dsp_cost)) {
                rw_itp_coeff(row, col) = dsp_cost;
                continue;
            }

            if (raw_dsp == d_min || raw_dsp == d_max) {
                rw_itp_coeff(row, col) = dsp_cost;
                rw_mask(row, col) += cst_pandora_msk_pixel_stopped_interpolation;
                continue;
            }

            float sub_disp;
            float sub_cost;
            int valid;
            std::tie(sub_disp, sub_cost, valid) = method(
                py::array(
                    {3},
                    std::vector<float>{
                        r_cv(row, col, dsp-1),
                        r_cv(row, col, dsp),
                        r_cv(row, col, dsp+1)
                    }.data()
                ),
                raw_dsp,
                measure,
                cst_pandora_msk_pixel_stopped_interpolation
            );
            rw_disp(row, col) = raw_dsp + sub_disp / (float)subpixel;
            rw_itp_coeff(row, col) = sub_cost;
            rw_mask(row, col) += valid;
        }
    }

    return std::make_tuple(itp_coeff, disp, mask);

}


std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<int64_t>> loop_approximate_refinement(
    py::array_t<float> cv,
    py::array_t<float> disp,
    py::array_t<int64_t> mask,
    double d_min,
    double d_max,
    int subpixel,
    std::string measure,
    std::function<
        std::tuple<float, float, int>(py::array_t<float>, float, std::string, int)
    > &method,
    int64_t cst_pandora_msk_pixel_invalid, 
    int64_t cst_pandora_msk_pixel_stopped_interpolation 
) {
    auto r_cv = cv.unchecked<3>();
    auto rw_mask = mask.mutable_unchecked<2>();
    auto rw_disp = disp.mutable_unchecked<2>();
    size_t n_row = r_cv.shape(0);
    size_t n_col = r_cv.shape(1);
    size_t n_disp = r_cv.shape(2);

    py::array_t<float> itp_coeff = py::array_t<float>({n_row, n_col});
    auto rw_itp_coeff = itp_coeff.mutable_unchecked<2>();

    for (size_t row = 0; row < n_row; ++row) {
        for (size_t col = 0; col < n_col; ++col) {
            
            if ((rw_mask(row, col) & cst_pandora_msk_pixel_invalid) != 0) {
                rw_itp_coeff(row, col) = std::numeric_limits<float>::quiet_NaN();
                continue;
            }

            float raw_dsp = rw_disp(row, col);
            int dsp = (int)( (-raw_dsp - d_min) * subpixel );
            int diag = (int)(col + raw_dsp);
            float diag_cost = r_cv(row, diag, dsp);
            if (std::isnan(diag_cost)) {
                rw_itp_coeff(row, col) = diag_cost;
                continue;
            }

            if (raw_dsp == d_min || raw_dsp == d_max || diag == 0 || diag == n_col-1) {
                rw_itp_coeff(row, col) = diag_cost;
                rw_mask(row, col) += cst_pandora_msk_pixel_stopped_interpolation;
                continue;
            }

            float sub_disp;
            float sub_cost;
            int valid;
            std::tie(sub_disp, sub_cost, valid) = method(
                py::array(
                    {3},
                    std::vector<float>{
                        r_cv(row, diag, dsp-1),
                        r_cv(row, diag, dsp),
                        r_cv(row, diag, dsp+1)
                    }.data()
                ),
                raw_dsp,
                measure,
                cst_pandora_msk_pixel_stopped_interpolation
            );
            rw_disp(row, col) = raw_dsp + sub_disp / (float)subpixel;
            rw_itp_coeff(row, col) = sub_cost;
            rw_mask(row, col) += valid;
        }
    }

    return std::make_tuple(itp_coeff, disp, mask);

}