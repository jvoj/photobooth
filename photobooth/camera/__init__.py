#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Photobooth - a flexible photo booth software
# Copyright (C) 2018  Balthasar Reuter <photobooth at re - web dot eu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging

from PIL import Image, ImageOps
from io import BytesIO

from .PictureDimensions import PictureDimensions
from .. import StateMachine
from ..Threading import Workers

# Available camera modules as tuples of (config name, module name, class name)
modules = (
    ('python-gphoto2', 'CameraGphoto2', 'CameraGphoto2'),
    ('gphoto2-cffi', 'CameraGphoto2Cffi', 'CameraGphoto2Cffi'),
    ('gphoto2-commandline', 'CameraGphoto2CommandLine',
     'CameraGphoto2CommandLine'),
    ('opencv', 'CameraOpenCV', 'CameraOpenCV'),
    ('picamera', 'CameraPicamera', 'CameraPicamera'),
    ('dummy', 'CameraDummy', 'CameraDummy'))


class Camera:

    def __init__(self, config, comm, CameraModule):

        super().__init__()

        self._comm = comm
        self._cfg = config
        self._cam = CameraModule

        self._cap = None
        self._pic_dims = None

        self._is_preview = self._cfg.getBool('Photobooth', 'show_preview')
        self._is_keep_pictures = self._cfg.getBool('Storage', 'keep_pictures')

        rot_vals = {0: None, 90: Image.ROTATE_90, 180: Image.ROTATE_180,
                    270: Image.ROTATE_270}
        self._rotation = rot_vals[self._cfg.getInt('Camera', 'rotation')]

    def startup(self):

        self._cap = self._cam()

        logging.info('Using camera {} preview functionality'.format(
            'with' if self._is_preview else 'without'))

        test_picture = self._cap.getPicture()
        if self._rotation is not None:
            test_picture = test_picture.transpose(self._rotation)

        self._pic_dims = PictureDimensions(self._cfg, test_picture.size)
        self._is_preview = self._is_preview and self._cap.hasPreview

        background = self._cfg.get('Picture', 'background')
        if len(background) > 0:
            logging.info('Using background "{}"'.format(background))
            bg_picture = Image.open(background)
            self._template = bg_picture.resize(self._pic_dims.outputSize)
        else:
            self._template = Image.new('RGB', self._pic_dims.outputSize,
                                       (255, 255, 255))

        self.setIdle()
        self._comm.send(Workers.MASTER, StateMachine.CameraEvent('ready'))

    def teardown(self, state):

        if self._cap is not None:
            self._cap.cleanup()

    def run(self):

        for state in self._comm.iter(Workers.CAMERA):
            self.handleState(state)

        return True

    def handleState(self, state):

        if isinstance(state, StateMachine.StartupState):
            self.startup()
        elif isinstance(state, StateMachine.GreeterState):
            self.prepareCapture()
        elif isinstance(state, StateMachine.CountdownState):
            self.capturePreview()
        elif isinstance(state, StateMachine.CaptureState):
            self.capturePicture(state)
        elif isinstance(state, StateMachine.AssembleState):
            self.assemblePicture()
        elif isinstance(state, StateMachine.TeardownState):
            self.teardown(state)

    def setActive(self):

        self._cap.setActive()

    def setIdle(self):

        if self._cap.hasIdle:
            self._cap.setIdle()

    def prepareCapture(self):

        self.setActive()
        self._pictures = []

    def capturePreview(self):

        if self._is_preview:
            while self._comm.empty(Workers.CAMERA):
                picture = self._cap.getPreview()
                if self._rotation is not None:
                    picture = picture.transpose(self._rotation)
                picture = picture.resize(self._pic_dims.previewSize)
                picture = picture.crop((0, 52, self._pic_dims.previewSize[0], self._pic_dims.previewSize[1]-52));
                picture = ImageOps.mirror(picture)
                byte_data = BytesIO()
                picture.save(byte_data, format='jpeg')
                self._comm.send(Workers.GUI,
                                StateMachine.CameraEvent('preview', byte_data))

    def capturePicture(self, state):

        self.setIdle()
        picture = self._cap.getPicture()
        if self._rotation is not None:
            picture = picture.transpose(self._rotation)
        byte_data = BytesIO()
        picture.save(byte_data, format='jpeg')
        self._pictures.append(byte_data)
        self.setActive()

        if self._is_keep_pictures:
            self._comm.send(Workers.WORKER,
                            StateMachine.CameraEvent('capture', byte_data))

        if state.num_picture < self._pic_dims.totalNumPictures:
            self._comm.send(Workers.MASTER,
                            StateMachine.CameraEvent('countdown'))
        else:
            self._comm.send(Workers.MASTER,
                            StateMachine.CameraEvent('assemble'))

    def assemblePicture(self):

        self.setIdle()

        # assembled picture
        # 148 x 100 = 3496 x 2362
        # 900 x 600 preview

        picture = self._template.copy()

        # Jav edit jus tone pic
        shot = Image.open(self._pictures[0])
        print(self._pic_dims.thumbnailSize);
        resized = shot.resize(self._pic_dims.thumbnailSize)
        croped = resized.crop((0, 200, self._pic_dims.thumbnailSize[0], self._pic_dims.thumbnailSize[1]-300));
        picture.paste(croped, (self._pic_dims.thumbnailOffset[0][0], self._pic_dims.thumbnailOffset[0][1]))
        
        vetvicka = Image.open('vetvicka_rotated.png');
        jerab_ruzovy = Image.open('jerab_ruzovy_resized.png');
        jerab_fialovy = Image.open('jerab_fialovy_resized.png');
        pulvenec = Image.open('pulvenec_rotated.png');

        # pulvenec = pulvenec.rotate(90);
        picture.paste(vetvicka, (-100, -100), mask=vetvicka);
        picture.paste(jerab_ruzovy, (30, 1500), mask=jerab_ruzovy);
        picture.paste(jerab_fialovy, (2500, 1500), mask=jerab_fialovy);
        picture.paste(pulvenec, (2700, -100), mask=pulvenec);

        byte_data = BytesIO()
        picture.save(byte_data, format='jpeg')
        self._comm.send(Workers.MASTER,
                        StateMachine.CameraEvent('review', byte_data))
        self._pictures = []
