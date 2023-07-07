# -*- coding: utf-8 -*
'''!
  @file  DFRobot_CE30C.py
  @brief  Provides partial method functions
  @copyright  Copyright (c) 2010 DFRobot Co.Ltd (http://www.dfrobot.com)
  @license  The MIT License (MIT)
  @author  DFRobot
  @maintainer  [qsjhyy](yihuan.huang@dfrobot.com)
  @version  V1.0
  @date  2023-07-07
  @url  https://github.com/DFRobot/DFRobot_CE30C
'''
from __future__ import division   # Used to change integer division in python2
import math
import socket
import numpy as np

# Processing image data: undistortion.py

def _bilinear_interpolation(_targetX, _targetY, _p11, _p12, _p21, _p22):
    '''!
        @brief Perform bilinear interpolation to calculate the value at a target position.
        @param _targetX X-coordinate of the target position
        @param _targetY Y-coordinate of the target position
        @param _p11 Value at position (0, 0)
        @param _p12 Value at position (0, 1)
        @param _p21 Value at position (1, 0)
        @param _p22 Value at position (1, 1)
        @return Interpolated value at the target position
    '''
    alpha_x = _targetX % 1
    alpha_y = _targetY % 1
    interpl = int(_p11) * int(_p12) * int(_p21) * int(_p22)

    if interpl != 0:
        return (1 - alpha_x) * (1 - alpha_y) * _p11 + \
               alpha_x * (1 - alpha_y) * _p12 + \
               (1 - alpha_x) * alpha_y * _p21 + \
               alpha_x * alpha_y * _p22
    else:
        if alpha_x < 0.5 and alpha_y < 0.5:
            return _p11
        elif alpha_x >= 0.5 > alpha_y:
            return _p12
        elif alpha_x < 0.5 <= alpha_y:
            return _p21
        else:
            return _p22

def _remap(_src, _mapX, _mapY, _h, _w):
    '''!
        @brief Remap the source image using the provided mapping coordinates.
        @param _src Source image
        @param _mapX X-coordinate mapping
        @param _mapY Y-coordinate mapping
        @param _h Height of the remapped image
        @param _w Width of the remapped image
        @return Remapped image
    '''
    dst = np.empty((24, 660))

    for i in range(_h):
        for j in range(_w):
            targetX = _mapX[i, j]
            targetY = _mapY[i, j]
            x = int(targetX)
            y = int(targetY)
            if 0 <= y <= 22:
                p11 = _src[y, x]
                p12 = _src[y, x + 1]
                p21 = _src[y + 1, x]
                p22 = _src[y + 1, x + 1]
                dst[i, j] = _bilinear_interpolation(targetX, targetY, p11, p12, p21, p22)
            else:
                dst[i, j] = 0
    return dst

def _inverse_matrix(_A, _n):
    '''!
        @brief Calculate the inverse of a square matrix using Gaussian elimination.
        @param _A Square matrix to invert
        @param _n Size of the matrix
        @return Inverse of the matrix
    '''
    C = np.empty((_n, _n))
    _B = np.empty((_n, _n))

    for i in range(_n):
        for j in range(_n):
            C[i, j] = _A[i, j]
            _B[i, j] = 1.0 if i == j else 0.0

    for i in range(_n):
        temp = C[i, i]
        for j in range(_n):
            C[i, j] = C[i, j] / temp
            _B[i, j] = _B[i, j] / temp

        for j in range(_n):
            if j != i:
                it = C[j, i]
                for k in range(_n):
                    C[j, k] = C[j, k] - C[i, k] * it
                    _B[j, k] = _B[j, k] - _B[i, k] * it
    return _B

def _init_fisheye_map(_cameraMatrix, _coeffs, _height, _width):
    '''!
        @brief Initialize the fisheye distortion mapping.
        @param _cameraMatrix Camera matrix
        @param _coeffs Distortion coefficients
        @param _height Height of the fisheye map
        @param _width Width of the fisheye map
        @return Fisheye distortion mapping (_mapx, _mapy)
    '''
    _mapx = np.zeros((_height, _width), dtype=np.double)
    _mapy = np.zeros((_height, _width), dtype=np.double)

    newCameraMatrix = np.copy(_cameraMatrix)
    newCameraMatrix[0, 2] = (_width - 1) * 0.5
    newCameraMatrix[1, 2] = (_height - 1) * 0.5
    ir = _inverse_matrix(newCameraMatrix, 3)
    u0 = _cameraMatrix[0, 2]
    v0 = _cameraMatrix[1, 2]
    fx = _cameraMatrix[0, 0]
    fy = _cameraMatrix[1, 1]

    for i in range(_height):
        _x = i * ir[0, 1] + ir[0, 2]
        _y = i * ir[1, 1] + ir[1, 2]
        _w = i * ir[2, 1] + ir[2, 2]
        for j in range(_width):
            x = _x / _w
            y = _y / _w
            r = np.sqrt(x * x + y * y)
            theta = math.atan(r)
            theta_d = theta * (1 + _coeffs[0] * theta ** 2 + \
                               _coeffs[1] * theta ** 4 + \
                               _coeffs[2] * theta ** 6 + \
                               _coeffs[3] * theta ** 8)
            scale = 1.0 if r == 0 else theta_d / r
            _mapx[i, j] = fx * x * scale + u0
            _mapy[i, j] = fy * y * scale + v0

            _x += ir[0, 0]
            _y += ir[1, 0]
            _w += ir[2, 0]
    return [_mapx, _mapy]

# Data exchange, sending and receiving data: dataExchange.py

def _recvdata(tcp, _row, _colum):
    '''!
        @brief Receive data over TCP socket and convert it into a numpy array.
        @param tcp TCP socket object
        @param _row Number of rows in the array
        @param _colum Number of columns in the array
        @return Numpy array representing the received data
    '''
    string = ''
    bytes_read = 0
    bytes_n = _row * _colum * 2
    while bytes_read < bytes_n:
        try:
            chunk = tcp.recv(bytes_n - bytes_read)
        except socket.timeout:
            print("Receiver timeout")
            return None
        bytes_read += len(chunk)
        string += chunk
    array = np.fromstring(string, dtype=np.uint16)
    array.shape = (_row, _colum)
    return array

def _sendmsg(tcp, _msg):
    '''!
        @brief Send a message over a TCP socket.
        @param tcp TCP socket object
        @param _msg Message to send
    '''
    msg_len = len(_msg)
    total_sent = 0
    _msg += "\0" * (50 - msg_len)
    while total_sent < 50:
        chunk_len = tcp.send(_msg[total_sent:])
        total_sent += chunk_len

def _recvhex(tcp, _len):
    '''!
        @brief Receive hex-encoded data over a TCP socket and convert it into a numpy array.
        @param tcp TCP socket object
        @param _len Length of the received data
        @return Numpy array representing the received data
    '''
    string = ''
    bytes_read = 0
    while bytes_read < _len:
        try:
            chunk = tcp.recv(_len - bytes_read)
        except socket.timeout:
            print("Receiver timeout")
            return None
        bytes_read += len(chunk)
        string += chunk
    array = np.fromstring(string, dtype=np.ubyte)
    return array
