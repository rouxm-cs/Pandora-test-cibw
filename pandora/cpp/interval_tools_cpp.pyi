# pylint: skip-file
import numpy as np
from typing import Tuple

def create_connected_graph(border_left: np.ndarray, border_right: np.ndarray, depth: int) -> np.ndarray:
    """
    Create a boolean connection matrix from segment coordinates

    :param border_left: array containing the coordinates of segments left border
    :type border_left: (n, 2) np.ndarray where n is the number of segments
    :param border_right: array containing the coordinates of segments right border
    :type border_right: (n, 2) np.ndarray where n is the number of segments
    :param depth: the depth for regularization. It corresponds to the number of rows
        to explore below and above.
    :return: A symmetric boolean matrix of shape (n, n). 1 indicating that the segment are connected
    :rtype: np.ndarray of shape (n, n)
    """
    ...

def graph_regularization(
    interval_inf: np.ndarray,
    interval_sup: np.ndarray,
    border_left: np.ndarray,
    border_right: np.ndarray,
    connection_graph: np.ndarray,
    quantile: float,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Regularize the intervals based on quantiles and a given connection graph.

    :param interval_inf: The lower estimation of the disparity to regularize
    :type interval_inf: (row, col) np.ndarray
    :param interval_sup: The upper estimation of the disparity to regularize
    :type interval_sup: (row, col) np.ndarray
    :param border_left: array containing the coordinates of segments left border
    :type border_left: (n, 2) np.ndarray where n is the number of segments
    :param border_right: array containing the coordinates of segments right border
    :type border_right: (n, 2) np.ndarray where n is the number of segments
    :param connection graph: A matrix indicating if the segments (n in total) are connected
    :type connection graph: (n, n) boolean symmetric np.ndarray
    :param quantile: Which quantile to select for the regularized value
    :type quantile: float. 0 <= quantile <= 1
    :return: The regularized inf and sup of the disparity, and a boolean mask indicating regularization
    :rtype: Tuple[np.ndarray, np.ndarray, np.ndarray]
    """
    ...
