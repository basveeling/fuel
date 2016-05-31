from collections import OrderedDict
from io import BytesIO
import numpy
from numpy.testing import assert_raises, assert_allclose, assert_equal
from PIL import Image
from picklable_itertools.extras import partition_all
from six.moves import zip
from fuel.transformers._image import window_batch_bchw3d
from fuel import config
from fuel.datasets.base import IndexableDataset, IterableDataset
from fuel.schemes import ShuffledScheme, SequentialExampleScheme
from fuel.streams import DataStream
from fuel.transformers.image import (ImagesFromBytes, Image2DSlicer,
                                     MinimumImageDimensions,
                                     RandomFixedSizeCrop,
                                     RandomSpatialFlip, Drop,
                                     SamplewiseCropTransformer,
                                     FixedSizeCrop, FixedSizeCropND,
                                     Random2DRotation, GammaCorrectionND)


def reorder_axes(shp):
    if len(shp) == 3:
        shp = (shp[-1],) + shp[:-1]
    elif len(shp) == 2:
        shp = (1,) + shp
    return shp


class ImageTestingMixin(object):
    def common_setup(self):
        ex_scheme = SequentialExampleScheme(self.dataset.num_examples)
        self.example_stream = DataStream(self.dataset,
                                         iteration_scheme=ex_scheme)
        self.batch_size = 2
        scheme = ShuffledScheme(self.dataset.num_examples,
                                batch_size=self.batch_size)
        self.batch_stream = DataStream(self.dataset, iteration_scheme=scheme)


class TestImagesFromBytes(ImageTestingMixin):
    def setUp(self):
        rng = numpy.random.RandomState(config.default_seed)
        self.shapes = [
            (10, 12, 3),
            (9, 8, 4),
            (12, 14, 3),
            (4, 7),
            (9, 8, 4),
            (7, 9, 3)
        ]
        pil1 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[0])
                               .astype('uint8'), mode='RGB')
        pil2 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[1])
                               .astype('uint8'), mode='CMYK')
        pil3 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[2])
                               .astype('uint8'), mode='RGB')
        pil4 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[3])
                               .astype('uint8'), mode='L')
        pil5 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[4])
                               .astype('uint8'), mode='RGBA')
        pil6 = Image.fromarray(rng.random_integers(0, 255,
                                                   size=self.shapes[5])
                               .astype('uint8'), mode='YCbCr')
        source1 = [pil1, pil2, pil3]
        source2 = [pil4, pil5, pil6]
        bytesio1 = [BytesIO() for _ in range(3)]
        bytesio2 = [BytesIO() for _ in range(3)]
        formats1 = ['PNG', 'JPEG', 'BMP']
        formats2 = ['GIF', 'PNG', 'JPEG']
        for s, b, f in zip(source1, bytesio1, formats1):
            s.save(b, format=f)
        for s, b, f in zip(source2, bytesio2, formats2):
            s.save(b, format=f)
        self.dataset = IndexableDataset(
            OrderedDict([('source1', [b.getvalue() for b in bytesio1]),
                         ('source2', [b.getvalue() for b in bytesio2])]),
            axis_labels={'source1': ('batch', 'bytes'),
                         'source2': ('batch', 'bytes')})
        self.common_setup()

    def test_images_from_bytes_example_stream(self):
        stream = ImagesFromBytes(self.example_stream,
                                 which_sources=('source1', 'source2'),
                                 color_mode=None)
        s1, s2 = list(zip(*list(stream.get_epoch_iterator())))
        s1_shape = set(s.shape for s in s1)
        s2_shape = set(s.shape for s in s2)
        actual_s1 = set(reorder_axes(s) for s in self.shapes[:3])
        actual_s2 = set(reorder_axes(s) for s in self.shapes[3:])
        assert actual_s1 == s1_shape
        assert actual_s2 == s2_shape

    def test_images_from_bytes_batch_stream(self):
        stream = ImagesFromBytes(self.batch_stream,
                                 which_sources=('source1', 'source2'),
                                 color_mode=None)
        s1, s2 = list(zip(*list(stream.get_epoch_iterator())))
        s1 = sum(s1, [])
        s2 = sum(s2, [])
        s1_shape = set(s.shape for s in s1)
        s2_shape = set(s.shape for s in s2)
        actual_s1 = set(reorder_axes(s) for s in self.shapes[:3])
        actual_s2 = set(reorder_axes(s) for s in self.shapes[3:])
        assert actual_s1 == s1_shape
        assert actual_s2 == s2_shape

    def test_images_from_bytes_example_stream_convert_rgb(self):
        stream = ImagesFromBytes(self.example_stream,
                                 which_sources=('source1', ),
                                 color_mode='RGB')
        s1, s2 = list(zip(*list(stream.get_epoch_iterator())))
        actual_s1_gen = (reorder_axes(s) for s in self.shapes[:3])
        actual_s1 = set((3,) + s[1:] for s in actual_s1_gen)
        s1_shape = set(s.shape for s in s1)
        assert actual_s1 == s1_shape

    def test_images_from_bytes_example_stream_convert_l(self):
        stream = ImagesFromBytes(self.example_stream,
                                 which_sources=('source2', ),
                                 color_mode='L')
        s1, s2 = list(zip(*list(stream.get_epoch_iterator())))
        actual_s2_gen = (reorder_axes(s) for s in self.shapes[3:])
        actual_s2 = set((1,) + s[1:] for s in actual_s2_gen)
        s2_shape = set(s.shape for s in s2)
        assert actual_s2 == s2_shape

    def test_axis_labels(self):
        stream = ImagesFromBytes(self.example_stream,
                                 which_sources=('source2',))
        assert stream.axis_labels['source1'] == ('bytes',)
        assert stream.axis_labels['source2'] == ('channel', 'height',
                                                 'width')
        bstream = ImagesFromBytes(self.batch_stream,
                                  which_sources=('source1',))
        assert bstream.axis_labels['source1'] == ('batch', 'channel', 'height',
                                                  'width')
        assert bstream.axis_labels['source2'] == ('batch', 'bytes')

    def test_bytes_type_exception(self):
        stream = ImagesFromBytes(self.example_stream,
                                 which_sources=('source2',))
        assert_raises(TypeError, stream.transform_source_example, 54321,
                      'source2')


class TestMinimumDimensions(ImageTestingMixin):
    def setUp(self):
        rng = numpy.random.RandomState(config.default_seed)
        source1 = []
        source2 = []
        source3 = []
        self.shapes = [(5, 9), (4, 6), (4, 3), (6, 4), (2, 5), (4, 8), (8, 3)]
        for i, shape in enumerate(self.shapes):
            source1.append(rng.normal(size=shape))
            source2.append(rng.normal(size=shape[::-1]))
            source3.append(rng.random_integers(0, 255, size=(3,) + shape)
                           .astype('uint8'))
        self.dataset = IndexableDataset(OrderedDict([('source1', source1),
                                                     ('source2', source2),
                                                     ('source3', source3)]),
                                        axis_labels={'source1':
                                                     ('batch', 'channel',
                                                      'height', 'width'),
                                                     'source3':
                                                     ('batch', 'channel',
                                                      'height', 'width')})
        self.common_setup()

    def test_minimum_dimensions_example_stream(self):
        stream = MinimumImageDimensions(self.example_stream, (4, 5),
                                        which_sources=('source1',
                                                       'source3'))
        it = stream.get_epoch_iterator()
        for example, shp in zip(it, self.shapes):
            assert example[0].shape[0] >= 4 and example[0].shape[1] >= 5
            assert (example[1].shape[1] == shp[0] and
                    example[1].shape[0] == shp[1])
            assert example[2].shape[0] == 3
            assert example[2].shape[1] >= 4 and example[2].shape[2] >= 5

    def test_minimum_dimensions_batch_stream(self):
        stream = MinimumImageDimensions(self.batch_stream, (4, 5),
                                        which_sources=('source1',))
        it = stream.get_epoch_iterator()
        for batch, shapes in zip(it, partition_all(self.batch_size,
                                                   self.shapes)):
            assert (example.shape[0] >= 4 and example.shape[1] >= 5
                    for example in batch[0])
            assert (example.shape[1] == shp[0] and
                    example.shape[0] == shp[1]
                    for example, shp in zip(batch[1], shapes))

    def test_axes_exception(self):
        stream = MinimumImageDimensions(self.example_stream, (4, 5),
                                        which_sources=('source1',))
        assert_raises(NotImplementedError,
                      stream.transform_source_example,
                      numpy.empty((2, 3, 4, 2)),
                      'source1')

    def test_resample_exception(self):
        assert_raises(ValueError,
                      MinimumImageDimensions, self.example_stream, (4, 5),
                      resample='notarealresamplingmode')


class TestFixedSizeRandomCrop(ImageTestingMixin):
    def setUp(self):
        source1 = numpy.zeros((9, 3, 7, 5), dtype='uint8')
        source1[:] = numpy.arange(3 * 7 * 5, dtype='uint8').reshape(3, 7, 5)
        shapes = [(5, 9), (6, 8), (5, 6), (5, 5), (6, 4), (7, 4),
                  (9, 4), (5, 6), (6, 5)]
        source2 = []
        biggest = 0
        num_channels = 2
        for shp in shapes:
            biggest = max(biggest, shp[0] * shp[1] * 2)
            ex = numpy.arange(shp[0] * shp[1] * num_channels).reshape(
                (num_channels,) + shp).astype('uint8')
            source2.append(ex)
        self.source2_biggest = biggest
        axis_labels = {'source1': ('batch', 'channel', 'height', 'width'),
                       'source2': ('batch', 'channel', 'height', 'width')}
        self.dataset = IndexableDataset(OrderedDict([('source1', source1),
                                                     ('source2', source2)]),
                                        axis_labels=axis_labels)
        self.common_setup()

    def test_ndarray_batch_source(self):
        # Make sure that with enough epochs we sample everything.
        stream = RandomFixedSizeCrop(self.batch_stream, (5, 4),
                                     which_sources=('source1',))
        seen_indices = numpy.array([], dtype='uint8')
        for i in range(30):
            for batch in stream.get_epoch_iterator():
                assert batch[0].shape[1:] == (3, 5, 4)
                assert batch[0].shape[0] in (1, 2)
                seen_indices = numpy.union1d(seen_indices, batch[0].flatten())
            if 3 * 7 * 5 == len(seen_indices):
                break
        else:
            assert False

    def test_list_batch_source(self):
        # Make sure that with enough epochs we sample everything.
        stream = RandomFixedSizeCrop(self.batch_stream, (5, 4),
                                     which_sources=('source2',))
        seen_indices = numpy.array([], dtype='uint8')
        for i in range(30):
            for batch in stream.get_epoch_iterator():
                for example in batch[1]:
                    assert example.shape == (2, 5, 4)
                    seen_indices = numpy.union1d(seen_indices,
                                                 example.flatten())
                assert len(batch[1]) in (1, 2)
            if self.source2_biggest == len(seen_indices):
                break
        else:
            assert False

    def test_format_exceptions(self):
        estream = RandomFixedSizeCrop(self.example_stream, (5, 4),
                                      which_sources=('source2',))
        bstream = RandomFixedSizeCrop(self.batch_stream, (5, 4),
                                      which_sources=('source2',))
        assert_raises(ValueError, estream.transform_source_example,
                      numpy.empty((5, 6)), 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((7, 6))], 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((8, 6))], 'source2')

    def test_window_too_big_exceptions(self):
        stream = RandomFixedSizeCrop(self.example_stream, (5, 4),
                                     which_sources=('source2',))

        assert_raises(ValueError, stream.transform_source_example,
                      numpy.empty((3, 4, 2)), 'source2')

        bstream = RandomFixedSizeCrop(self.batch_stream, (5, 4),
                                      which_sources=('source1',))

        assert_raises(ValueError, bstream.transform_source_batch,
                      numpy.empty((5, 3, 4, 2)), 'source1')


class TestRandom2DRotation(ImageTestingMixin):
    def setUp(self):
        source1 = numpy.zeros((2, 3, 4, 5), dtype='uint8')
        source1[:] = numpy.arange(3 * 4 * 5, dtype='uint8').reshape((3, 4, 5))

        source2 = numpy.empty(2, dtype=object)
        source2[0] = numpy.arange(3 * 4 * 5, dtype='uint8').reshape((3, 4, 5))
        source2[1] = numpy.arange(3 * 4 * 6, dtype='uint8').reshape((3, 4, 6))

        source3 = [source2[0], source2[1]]

        self.source1 = source1
        self.source2 = source2
        self.source3 = source3

        axis_labels = {'source1': ('batch', 'channel', 'height', 'width'),
                       'source2': ('batch', 'channel', 'height', 'width'),
                       'source3': ('batch', 'channel', 'height', 'width')}
        self.dataset = \
            IndexableDataset(OrderedDict([('source1', source1),
                                          ('source2', source2),
                                          ('source3', source3)]),
                             axis_labels=axis_labels)
        self.common_setup()

    def test_format_exceptions(self):
        estream = Random2DRotation(self.example_stream,
                                   which_sources=('source2',))
        bstream = Random2DRotation(self.batch_stream,
                                   which_sources=('source2',))
        assert_raises(ValueError, estream.transform_source_example,
                      numpy.empty((5, 6)), 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((7, 6))], 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((8, 6))], 'source2')

    def test_maximum_rotation_invalid_exception(self):
        assert_raises(ValueError, Random2DRotation, self.example_stream,
                      maximum_rotation=0.0,
                      which_sources=('source2',))
        assert_raises(ValueError, Random2DRotation, self.example_stream,
                      maximum_rotation=3.1416,
                      which_sources=('source2',))

    def test_invalid_resample_exception(self):
        assert_raises(ValueError, Random2DRotation, self.example_stream,
                      resample='nonexisting')

    def test_random_2D_rotation_example_stream(self):
        maximum_rotation = 0.5
        rng = numpy.random.RandomState(123)
        estream = Random2DRotation(self.example_stream,
                                   maximum_rotation,
                                   rng=rng,
                                   which_sources=('source1',))
        # the C x X x Y image should have equal rotation for all c in C
        out = estream.transform_source_example(self.source1[0], 'source1')
        expected = numpy.array([[[0,  0,  0,  2,  3],
                                 [0,  0,  1,  7,  8],
                                 [0,  5,  6, 12, 13],
                                 [0, 10, 11, 17, 18]],
                                [[0,  0,  0, 22, 23],
                                 [0, 20, 21, 27, 28],
                                 [0, 25, 26, 32, 33],
                                 [0, 30, 31, 37, 38]],
                                [[0,  0,  0, 42, 43],
                                 [0, 40, 41, 47, 48],
                                 [0, 45, 46, 52, 53],
                                 [0, 50, 51, 57, 58]]], dtype='uint8')
        assert_equal(out, expected)

    def test_random_2D_rotation_batch_stream(self):
        rng = numpy.random.RandomState(123)
        bstream = Random2DRotation(self.batch_stream,
                                   maximum_rotation=0.5,
                                   rng=rng,
                                   which_sources=('source1',))
        # each C x X x Y image should have equal rotation for all c in C
        out = bstream.transform_source_batch(self.source1, 'source1')
        expected = numpy.array([[[[0,  0,  0,  2,  3],
                                  [0,  0,  1,  7,  8],
                                  [0,  5,  6, 12, 13],
                                  [0, 10, 11, 17, 18]],
                                 [[0,  0,  0, 22, 23],
                                  [0, 20, 21, 27, 28],
                                  [0, 25, 26, 32, 33],
                                  [0, 30, 31, 37, 38]],
                                 [[0,  0,  0, 42, 43],
                                  [0, 40, 41, 47, 48],
                                  [0, 45, 46, 52, 53],
                                  [0, 50, 51, 57, 58]]],
                                [[[0,  0,  1,  0,  0],
                                  [0,  5,  6,  2,  3],
                                  [0, 10, 11,  7,  8],
                                  [0, 15, 16, 12, 13]],
                                 [[0, 20, 21,  0,  0],
                                  [0, 25, 26, 22, 23],
                                  [0, 30, 31, 27, 28],
                                  [0, 35, 36, 32, 33]],
                                 [[0, 40, 41,  0,  0],
                                  [0, 45, 46, 42, 43],
                                  [0, 50, 51, 47, 48],
                                  [0, 55, 56, 52, 53]]]], dtype='uint8')
        assert_equal(out, expected)

        expected = \
            [numpy.array([[[0,  0,  0,  2,   3],
                           [0,  0,  1,  7,   8],
                           [0,  5,  6,  12, 13],
                           [0,  10, 11, 17, 18]],
                          [[0,  0,  0,  22, 23],
                           [0,  20, 21, 27, 28],
                           [0,  25, 26, 32, 33],
                           [0,  30, 31, 37, 38]],
                          [[0,  0,  0,  42, 43],
                           [0,  40, 41, 47, 48],
                           [0,  45, 46, 52, 53],
                           [0,  50, 51, 57, 58]]], dtype='uint8'),
             numpy.array([[[0,  0,  1,  2,  0,   0],
                           [0,  6,  7,  8,  3,   4],
                           [12, 13, 14, 15, 9,  10],
                           [18, 19, 20, 15, 16, 17]],
                          [[0,  24, 25, 26,  0,  0],
                           [0,  30, 31, 32, 27, 28],
                           [36, 37, 38, 39, 33, 34],
                           [42, 43, 44, 39, 40, 41]],
                          [[0,  48, 49, 50,  0,  0],
                           [0,  54, 55, 56, 51, 52],
                           [60, 61, 62, 63, 57, 58],
                           [66, 67, 68, 63, 64, 65]]], dtype='uint8')]

        rng = numpy.random.RandomState(123)
        bstream = Random2DRotation(self.batch_stream,
                                   maximum_rotation=0.5,
                                   rng=rng,
                                   which_sources=('source2',))
        out = bstream.transform_source_batch(self.source2, 'source2')
        assert_equal(out[0], expected[0])
        assert_equal(out[1], expected[1])

        rng = numpy.random.RandomState(123)
        bstream = Random2DRotation(self.batch_stream,
                                   maximum_rotation=0.5,
                                   rng=rng,
                                   which_sources=('source3',))
        out = bstream.transform_source_batch(self.source3, 'source3')
        assert_equal(out[0], expected[0])
        assert_equal(out[1], expected[1])

    def test_random_2D_rotation_example_stream_float(self):
        maximum_rotation = 0.5
        rng = numpy.random.RandomState(123)
        estream = Random2DRotation(self.example_stream,
                                   maximum_rotation,
                                   rng=rng,
                                   which_sources=('source1',))
        # the C x X x Y image should have equal rotation for all c in C
        out = estream.transform_source_example(self.source1[0].
                                               astype('float32'),
                                               'source1')
        expected = numpy.array([[[0,  0,  0,  2,  3],
                                 [0,  0,  1,  7,  8],
                                 [0,  5,  6, 12, 13],
                                 [0, 10, 11, 17, 18]],
                                [[0,  0,  0, 22, 23],
                                 [0, 20, 21, 27, 28],
                                 [0, 25, 26, 32, 33],
                                 [0, 30, 31, 37, 38]],
                                [[0,  0,  0, 42, 43],
                                 [0, 40, 41, 47, 48],
                                 [0, 45, 46, 52, 53],
                                 [0, 50, 51, 57, 58]]], dtype='float32')
        assert_equal(out, expected)


class TestRandomSpatialFlip(ImageTestingMixin):

    def setUp(self):

        # source is list of np.array with dim 3
        self.source_list = [
            numpy.array([[[1, 0],
                          [0, 2]],

                         [[3, 0],
                          [0, 4]]]),

            numpy.array([[[1, 2, 3],
                          [0, 0, 0]],

                         [[4, 5, 6],
                          [0, 0, 0]]])
        ]
        # source is np.object of np.array with dim 3
        self.source_ndobject = numpy.empty((2,), dtype=object)
        self.source_ndobject[0] = numpy.array([[[1, 0],
                                                [0, 2]],

                                               [[3, 0],
                                                [0, 4]]])

        self.source_ndobject[1] = numpy.array([[[1, 2, 3],
                                                [0, 0, 0]],

                                               [[4, 5, 6],
                                                [0, 0, 0]]])

        # source is np.array with dim 4
        self.source_ndarray = numpy.array([
            [[[1, 2, 3],
              [0, 0, 0]],

             [[4, 5, 6],
              [0, 0, 0]]],

            [[[1, 2, 3],
              [0, 0, 0]],

             [[4, 5, 6],
              [0, 0, 0]]]
        ])

        self.dataset = IndexableDataset(OrderedDict([
                ('source_list', self.source_list),
                ('source_ndobject', self.source_ndobject),
                ('source_ndarray', self.source_ndarray)
            ]))

        self.common_setup()

    def test_list_batch_source(self):

        source = self.source_list
        source_name = 'source_list'

        seed = 10
        # to_flip_h = [1, 0]
        # to_flip_h = [1, 1]

        # test no flip
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = source
        all(assert_allclose(ex_result, ex_expected, err_msg="Mismatch no flip")
            for ex_result, ex_expected in zip(result, expected))

        # test flip horizontally
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = [
            numpy.array([[[0, 1],
                          [2, 0]],

                         [[0, 3],
                          [4, 0]]]),

            numpy.array([[[1, 2, 3],
                          [0, 0, 0]],

                         [[4, 5, 6],
                          [0, 0, 0]]])
        ]
        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip horizontally")
            for ex_result, ex_expected in zip(result, expected))

        # test flip vertically
        rng = numpy.random.RandomState(seed=seed)
        rng.binomial(n=1, p=0.5, size=len(source))  # simulate first rng call
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = [
            numpy.array([[[0, 2],
                          [1, 0]],

                         [[0, 4],
                          [3, 0]]]),

            numpy.array([[[0, 0, 0],
                          [1, 2, 3]],

                         [[0, 0, 0],
                          [4, 5, 6]]])
        ]
        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip vertically")
            for ex_result, ex_expected in zip(result, expected))

        # test flip both
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True, flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = [
            numpy.array([[[2, 0],
                          [0, 1]],

                         [[4, 0],
                          [0, 3]]]),

            numpy.array([[[0, 0, 0],
                          [1, 2, 3]],

                         [[0, 0, 0],
                          [4, 5, 6]]])
        ]
        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip both")
            for ex_result, ex_expected in zip(result, expected))

    def test_ndobject_batch_source(self):

        source = self.source_ndobject
        source_name = 'source_ndobject'
        expected = numpy.empty((2,), dtype=object)

        seed = 10
        # to_flip_h = [1, 0]
        # to_flip_v = [1, 1]

        # test no flip
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = numpy.copy(source)
        all(assert_allclose(ex_result, ex_expected, err_msg="Mismatch no flip")
            for ex_result, ex_expected in zip(result, expected))

        # test flip horizontally
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected[0] = numpy.array([[[0, 1],
                                    [2, 0]],

                                   [[0, 3],
                                    [4, 0]]])
        expected[1] = numpy.array([[[1, 2, 3],
                                    [0, 0, 0]],

                                   [[4, 5, 6],
                                    [0, 0, 0]]])

        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip horizontally")
            for ex_result, ex_expected in zip(result, expected))

        # test flip vertically
        rng = numpy.random.RandomState(seed=seed)
        rng.binomial(n=1, p=0.5, size=source.shape[0])  # force first rng call
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected[0] = numpy.array([[[0, 2],
                                    [1, 0]],

                                   [[0, 4],
                                    [3, 0]]])
        expected[1] = numpy.array([[[0, 0, 0],
                                    [1, 2, 3]],

                                   [[0, 0, 0],
                                    [4, 5, 6]]])
        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip vertically")
            for ex_result, ex_expected in zip(result, expected))

        # test flip both
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True, flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected[0] = numpy.array([[[2, 0],
                                    [0, 1]],

                                   [[4, 0],
                                    [0, 3]]])
        expected[1] = numpy.array([[[0, 0, 0],
                                    [1, 2, 3]],

                                   [[0, 0, 0],
                                    [4, 5, 6]]])

        all(assert_allclose(ex_result, ex_expected,
                            err_msg="Mismatch flip both")
            for ex_result, ex_expected in zip(result, expected))

    def test_ndarray_batch_source(self):

        source = self.source_ndarray
        source_name = 'source_ndarray'

        seed = 10
        # to_flip_h = [1, 0]
        # to_flip_h = [1, 1]

        # test no flip
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = source
        assert_allclose(result, expected, err_msg="Mismatch no flip")

        # test flip horizontally
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = numpy.array([
            [[[3, 2, 1],
              [0, 0, 0]],

             [[6, 5, 4],
              [0, 0, 0]]],

            [[[1, 2, 3],
              [0, 0, 0]],

             [[4, 5, 6],
              [0, 0, 0]]]
        ])
        assert_allclose(result, expected, err_msg="Mismatch flip horizontally")

        # test flip vertically
        rng = numpy.random.RandomState(seed=seed)
        rng.binomial(n=1, p=0.5, size=source.shape[0])  # force first rng call
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = numpy.array([
            [[[0, 0, 0],
              [1, 2, 3]],

             [[0, 0, 0],
              [4, 5, 6]]],

            [[[0, 0, 0],
              [1, 2, 3]],

             [[0, 0, 0],
              [4, 5, 6]]]
        ])
        assert_allclose(result, expected, err_msg="Mismatch flip vertically")

        # test flip both
        rng = numpy.random.RandomState(seed=seed)
        stream = RandomSpatialFlip(self.example_stream,
                                   flip_h=True, flip_v=True,
                                   which_sources=(source_name,),
                                   rng=rng)
        result = stream.transform_source_batch(source, source_name)
        expected = numpy.array([
            [[[0, 0, 0],
              [3, 2, 1]],

             [[0, 0, 0],
              [6, 5, 4]]],

            [[[0, 0, 0],
              [1, 2, 3]],

             [[0, 0, 0],
              [4, 5, 6]]]
        ])
        assert_allclose(result, expected, err_msg="Mismatch flip both")


class TestSamplewiseCropTransformer(object):
    def setUp(self):
        self.sources = ['volume1', 'volume2', 'weight']
        self.weight_source = 'weight'
        self.shape = (5, 5, 5)
        self.window_shape = (2, 2, 2)

        self.data_volume1 = [0 for x in range(10)]
        self.data_volume2 = [0 for x in range(10)]
        self.data_weight = [0 for x in range(10)]

        for k in range(10):
            self.data_volume1[k] = numpy.arange(numpy.prod(self.shape))\
                .reshape([1, 1] + list(self.shape)).astype(numpy.float32)
            self.data_volume2[k] = numpy.arange(numpy.prod(self.shape))\
                .reshape([1, 1] + list(self.shape)).astype(numpy.float32)
            self.data_weight[k] = numpy.random.uniform(size=self.shape)\
                .reshape([1, 1] + list(self.shape)).astype(numpy.float32)

        self.data = OrderedDict([('volume1', self.data_volume1),
                                 ('volume2', self.data_volume2),
                                 ('weight', self.data_weight)])

        self.stream = DataStream(IterableDataset(self.data))
        self.stream.produces_examples = False
        self.swctransformer = SamplewiseCropTransformer(self.stream,
                                                        self.window_shape)
        self.volume = numpy.arange(5 * 5 * 5).reshape((1, 1) + (5, 5, 5))\
            .astype(numpy.float32)
        self.image = numpy.arange(5 * 5).reshape((1, 1) + (5, 5))\
            .astype(numpy.float32)
        self.source_ndobject = numpy.empty((2,), dtype=object)
        self.source_ndobject[0] = self.volume[0]
        self.source_ndobject[1] = self.volume[0]
        self.seed = 123
        self.rng = numpy.random.RandomState(self.seed)

    def test_no_weight_crop(self):
        epoch_iterat = self.swctransformer.get_epoch_iterator()

        former_crop = []
        different = []
        for k in range(5):
            n = next(epoch_iterat)
            # Test if new array size is compliant to window_shape
            for k in range(3):
                assert n[k].shape[2:] == self.window_shape
            # Test if the crop is similar on all volumes of the sample
            assert_allclose(n[0], n[1])
            # Test if random crop different from former random crop
            different.append(former_crop == n[0])
            former_crop = n[0]

    def test_no_weight_which_sources(self):
        swctransformer = SamplewiseCropTransformer(self.stream,
                                                   self.window_shape,
                                                   which_sources=['volume1'],
                                                   weight_source=None)
        epoch_iterat = swctransformer.get_epoch_iterator()
        for k in range(5):
            n = next(epoch_iterat)
            # Test if only sources directed by "which_sources" are affected
            assert n[0].shape == (1, 1) + self.window_shape
            assert n[1].shape == (1, 1) + self.shape
            assert n[2].shape == (1, 1) + self.shape

    def test_calculate_heatmap(self):
        # Test calculate heatmap on 3D images
        new_volume = self.swctransformer.calculate_heatmap(self.volume)
        assert_allclose(new_volume,
                        self.volume / self.volume[:, :, 2:-1, 2:-1, 2:-1]
                        .sum())
        new_image = self.swctransformer.calculate_heatmap(self.image)
        assert_allclose(new_image,
                        self.image / self.image[:, :, 2:-1, 2:-1].sum())

    def test_transform_source_batch(self):
        # Test randint initialization

        # Unspecified randint
        # Cropping through transformer
        new_volume = self.swctransformer.transform_source_batch(self.volume,
                                                                'any', None)
        # Cropping manually
        rng = numpy.random.RandomState(config.default_seed)
        out = numpy.empty(self.volume.shape[:2] + self.window_shape,
                          dtype=self.volume.dtype)
        max_indices = {}
        offsets = {}
        for i in range(len(self.window_shape)):
            max_indices[i] = self.volume.shape[2:][i] - self.window_shape[i]
            offsets[i] = rng.random_integers(0, max_indices[i],
                                             size=1)
        window_batch_bchw3d(self.volume, offsets[0], offsets[1], offsets[2],
                            out)
        assert_allclose(out, new_volume)

        # Specified randint
        # Cropping through transformer
        new_volume = self.swctransformer.transform_source_batch(self.volume,
                                                                'any',
                                                                self.seed)
        # Cropping manually
        out = numpy.empty(self.volume.shape[:2] + self.window_shape,
                          dtype=self.volume.dtype)
        max_indices = {}
        offsets = {}
        for i in range(len(self.window_shape)):
            max_indices[i] = self.volume.shape[2:][i] - self.window_shape[i]
            offsets[i] = self.rng.random_integers(0, max_indices[i],
                                                  size=1)
        window_batch_bchw3d(self.volume, offsets[0], offsets[1], offsets[2],
                            out)
        assert_allclose(out, new_volume)

        # Test sourcedtype
        npy_obj = numpy.empty(2, dtype=object)
        npy_obj[0] = self.volume[0]
        npy_obj[1] = self.volume[0]
        # Through transformer
        result = self.swctransformer.transform_source_batch(npy_obj, 'kappa',
                                                            self.seed)
        # Manually
        expected = numpy.array(
            [self.swctransformer.transform_source_example(npy_obj[0],
                                                          'kappa', self.seed),
             self.swctransformer.transform_source_example(npy_obj[1],
                                                          'kappa', self.seed)])

        assert_allclose(result, expected)

        # Testing consitency of window shape and volume shape
        kwargs = {'source': self.image,
                  'source_name': 'kappa',
                  'seed': self.seed}
        assert_raises(ValueError,
                      self.swctransformer.transform_source_batch,
                      **kwargs)

    def test_transform_source_example(self):
        # Testing consitency of window shape and volume shape
        kwargs = {'example': numpy.arange(1).reshape((1, 1, 1, 1)),
                  'source_name': 'kappa',
                  'seed': self.seed}
        assert_raises(ValueError,
                      self.swctransformer.transform_source_example,
                      **kwargs)

        # Test cropping of 2D images
        # Transformer cropping
        swctransformer = SamplewiseCropTransformer(self.stream,
                                                   (2, 2))
        result = swctransformer.transform_source_example(self.image[0],
                                                         'kappa',
                                                         self.seed)
        # Manual cropping
        max_indices = {}
        offsets = {}
        for i in range(len(swctransformer.window_shape)):
            max_indices[i] = \
                self.image[0].shape[1:][i] - \
                swctransformer.window_shape[i]
            offsets[i] = self.rng.random_integers(0, max_indices[i])
        expected = self.image[0][
            :,
            offsets[0]:offsets[0] + swctransformer.window_shape[0],
            offsets[1]:offsets[1] + swctransformer.window_shape[1]]
        assert_allclose(result, expected)


class TestFixedSizeCrop(ImageTestingMixin):
    def setUp(self):
        source1 = numpy.zeros((9, 3, 7, 5), dtype='uint8')
        source1[:] = numpy.arange(3 * 7 * 5, dtype='uint8').reshape(3, 7, 5)
        shapes = [(5, 8), (6, 8), (5, 6), (5, 5), (6, 4), (7, 4),
                  (9, 4), (5, 6), (6, 5)]
        source2 = []
        biggest = 0
        num_channels = 2
        for shp in shapes:
            biggest = max(biggest, shp[0] * shp[1] * 2)
            ex = numpy.arange(shp[0] * shp[1] * num_channels).reshape(
                (num_channels,) + shp).astype('uint8')
            source2.append(ex)
        self.source2_biggest = biggest
        source3 = numpy.empty((len(shapes),), dtype=object)
        for i in range(len(source2)):
            source3[i] = source2[i]
        axis_labels = {'source1': ('batch', 'channel', 'height', 'width'),
                       'source2': ('batch', 'channel', 'height', 'width'),
                       'source3': ('batch', 'channel', 'height', 'width')}
        self.dataset = IndexableDataset(OrderedDict([('source1', source1),
                                                     ('source2', source2),
                                                     ('source3', source3)]),
                                        axis_labels=axis_labels)
        self.common_setup()

    def test_ndarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')
        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCrop(self.batch_stream, (5, 4),
                                   which_sources=('source1',), location=loc)
            # seen indices should only be of that length in after last location
            if 3 * 7 * 5 == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                assert batch[0].shape[1:] == (3, 5, 4)
                assert batch[0].shape[0] in (1, 2)
                seen_indices = numpy.union1d(seen_indices, batch[0].flatten())
        assert 3 * 7 * 5 == len(seen_indices)

    def test_list_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')

        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCrop(self.batch_stream, (5, 4),
                                   which_sources=('source2',), location=loc)
            # seen indices should only be of that length in after last location
            if self.source2_biggest == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                for example in batch[1]:
                    assert example.shape == (2, 5, 4)
                    seen_indices = numpy.union1d(seen_indices,
                                                 example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_objectarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')

        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCrop(self.batch_stream, (5, 4),
                                   which_sources=('source3',), location=loc)
            # seen indices should only be of that length in after last location
            if self.source2_biggest == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                for example in batch[2]:
                    assert example.shape == (2, 5, 4)
                    seen_indices = numpy.union1d(seen_indices,
                                                 example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_wrong_location_exceptions(self):
        assert_raises(ValueError, FixedSizeCrop, self.example_stream, (5, 4),
                      which_sources=('source2',), location=1)
        assert_raises(ValueError, FixedSizeCrop, self.example_stream, (5, 4),
                      which_sources=('source2',), location=[0, 1, 0])
        assert_raises(ValueError, FixedSizeCrop, self.example_stream, (5, 4),
                      which_sources=('source2',), location=[2, 0])

    def test_format_exceptions(self):
        estream = FixedSizeCrop(self.example_stream, (5, 4),
                                which_sources=('source2',), location=[0, 0])
        bstream = FixedSizeCrop(self.batch_stream, (5, 4),
                                which_sources=('source2',), location=[0, 0])
        assert_raises(ValueError, estream.transform_source_example,
                      numpy.empty((5, 6)), 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((7, 6))], 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((8, 6))], 'source2')

    def test_window_too_big_exceptions(self):
        stream = FixedSizeCrop(self.example_stream, (5, 4),
                               which_sources=('source2',), location=[0, 0])

        assert_raises(ValueError, stream.transform_source_example,
                      numpy.empty((3, 4, 2)), 'source2')

        bstream = FixedSizeCrop(self.batch_stream, (5, 4),
                                which_sources=('source1',), location=[0, 0])

        assert_raises(ValueError, bstream.transform_source_batch,
                      numpy.empty((5, 3, 4, 2)), 'source1')


class TestFixedSizeCropND_3D(ImageTestingMixin):
    def setUp(self):
        source1 = numpy.zeros((9, 3, 7, 5, 4), dtype='uint16')
        source1[:] = numpy.arange(3 * 7 * 5 * 4, dtype='uint16')\
            .reshape((3, 7, 5, 4))
        shapes = [(5, 8, 4), (6, 8, 3), (5, 6, 3), (5, 5, 4), (6, 4, 3),
                  (7, 4, 6), (9, 4, 4), (8, 6, 4), (6, 5, 3)]
        source2 = []
        biggest = 0
        num_channels = 2
        for shp in shapes:
            biggest = max(biggest, shp[0] * shp[1] * shp[2] * 2)
            ex = numpy.arange(shp[0] * shp[1] * shp[2] * num_channels).reshape(
                (num_channels,) + shp).astype('uint16')
            source2.append(ex)
        self.source2_biggest = biggest
        source3 = numpy.empty((len(shapes),), dtype=object)
        for i in range(len(source2)):
            source3[i] = source2[i]

        self.dataset = IndexableDataset(OrderedDict([('source1', source1),
                                                     ('source2', source2),
                                                     ('source3', source3)]))
        self.common_setup()

    def test_ndarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint16')
        for x in (0, 1):
            for y in (0, 1):
                for z in (0, 1):
                    stream = FixedSizeCropND(self.batch_stream, (5, 4, 3),
                                             which_sources=('source1',),
                                             location=(x, y, z))
                    # seen indices should only be of that length in
                    #  after last location
                    if 3 * 7 * 5 * 4 == len(seen_indices):
                        assert False
                    for batch in stream.get_epoch_iterator():
                        assert batch[0].shape[1:] == (3, 5, 4, 3)
                        assert batch[0].shape[0] in (1, 2)
                        seen_indices = numpy.union1d(seen_indices,
                                                     batch[0].flatten())
        assert 3 * 7 * 5 * 4 == len(seen_indices)

    def test_list_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint16')
        for x in (0, 1):
            for y in (0, 1):
                for z in (0, 1):
                    stream = FixedSizeCropND(self.batch_stream, (5, 4, 3),
                                             which_sources=('source2',),
                                             location=(x, y, z))
                    # seen indices should only be of that length
                    # in after last location
                    if self.source2_biggest == len(seen_indices):
                        assert False
                    for batch in stream.get_epoch_iterator():
                        for example in batch[1]:
                            assert example.shape == (2, 5, 4, 3)
                            seen_indices = numpy.union1d(seen_indices,
                                                         example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_objectarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint16')
        for x in (0, 1):
            for y in (0, 1):
                for z in (0, 1):
                    stream = FixedSizeCropND(self.batch_stream, (5, 4, 3),
                                             which_sources=('source3',),
                                             location=(x, y, z))
                    # seen indices should only be of that length
                    # in after last location
                    if self.source2_biggest == len(seen_indices):
                        assert False
                    for batch in stream.get_epoch_iterator():
                        for example in batch[2]:
                            assert example.shape == (2, 5, 4, 3)
                            seen_indices = numpy.union1d(seen_indices,
                                                         example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_wrong_format_exception(self):
        # Make sure transform_source_example returns ValueError if not example
        # is not a ndarray
        stream = FixedSizeCropND(self.batch_stream, (5, 4, 3),
                                 which_sources=('source3',),
                                 location=(0, 0, 0))
        assert_raises(ValueError, stream.transform_source_example, [5, 7],
                      'any')


class TestFixedSizeCropND_2D(ImageTestingMixin):
    """
    Test FixedSizeCropND with 2D images, same test as FixedSizeCrop
    """
    def setUp(self):
        source1 = numpy.zeros((9, 3, 7, 5), dtype='uint8')
        source1[:] = numpy.arange(3 * 7 * 5, dtype='uint8').reshape(3, 7, 5)
        shapes = [(5, 8), (6, 8), (5, 6), (5, 5), (6, 4), (7, 4),
                  (9, 4), (5, 6), (6, 5)]
        source2 = []
        biggest = 0
        num_channels = 2
        for shp in shapes:
            biggest = max(biggest, shp[0] * shp[1] * 2)
            ex = numpy.arange(shp[0] * shp[1] * num_channels).reshape(
                (num_channels,) + shp).astype('uint8')
            source2.append(ex)
        self.source2_biggest = biggest
        source3 = numpy.empty((len(shapes),), dtype=object)
        for i in range(len(source2)):
            source3[i] = source2[i]
        axis_labels = {'source1': ('batch', 'channel', 'height', 'width'),
                       'source2': ('batch', 'channel', 'height', 'width'),
                       'source3': ('batch', 'channel', 'height', 'width')}
        self.dataset = IndexableDataset(OrderedDict([('source1', source1),
                                                     ('source2', source2),
                                                     ('source3', source3)]),
                                        axis_labels=axis_labels)
        self.common_setup()

    def test_ndarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')
        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCropND(self.batch_stream, (5, 4),
                                     which_sources=('source1',), location=loc)
            # seen indices should only be of that length in after last location
            if 3 * 7 * 5 == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                assert batch[0].shape[1:] == (3, 5, 4)
                assert batch[0].shape[0] in (1, 2)
                seen_indices = numpy.union1d(seen_indices, batch[0].flatten())
        assert 3 * 7 * 5 == len(seen_indices)

    def test_list_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')

        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCropND(self.batch_stream, (5, 4),
                                     which_sources=('source2',), location=loc)
            # seen indices should only be of that length in after last location
            if self.source2_biggest == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                for example in batch[1]:
                    assert example.shape == (2, 5, 4)
                    seen_indices = numpy.union1d(seen_indices,
                                                 example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_objectarray_batch_source(self):
        # Make sure that with 4 corner crops we sample everything.
        seen_indices = numpy.array([], dtype='uint8')

        for loc in [(0, 0), (0, 1), (1, 0), (1, 1)]:
            stream = FixedSizeCropND(self.batch_stream, (5, 4),
                                     which_sources=('source3',), location=loc)
            # seen indices should only be of that length in after last location
            if self.source2_biggest == len(seen_indices):
                assert False
            for batch in stream.get_epoch_iterator():
                for example in batch[2]:
                    assert example.shape == (2, 5, 4)
                    seen_indices = numpy.union1d(seen_indices,
                                                 example.flatten())
        assert self.source2_biggest == len(seen_indices)

    def test_wrong_location_exceptions(self):
        assert_raises(ValueError, FixedSizeCropND, self.example_stream, (5, 4),
                      which_sources=('source2',), location=1)
        assert_raises(ValueError, FixedSizeCropND, self.example_stream, (5, 4),
                      which_sources=('source2',), location=[0, 1, 0])
        assert_raises(ValueError, FixedSizeCropND, self.example_stream, (5, 4),
                      which_sources=('source2',), location=[2, 0])

    def test_format_exceptions(self):
        estream = FixedSizeCropND(self.example_stream, (5, 4),
                                  which_sources=('source2',), location=[0, 0])
        bstream = FixedSizeCropND(self.batch_stream, (5, 4),
                                  which_sources=('source2',), location=[0, 0])
        assert_raises(ValueError, estream.transform_source_example,
                      numpy.empty((5, 6)), 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((7, 6))], 'source2')
        assert_raises(ValueError, bstream.transform_source_batch,
                      [numpy.empty((8, 6))], 'source2')

    def test_window_too_big_exceptions(self):
        stream = FixedSizeCropND(self.example_stream, (5, 4),
                                 which_sources=('source2',), location=[0, 0])

        assert_raises(ValueError, stream.transform_source_example,
                      numpy.empty((3, 4, 2)), 'source2')

        bstream = FixedSizeCropND(self.batch_stream, (5, 4),
                                  which_sources=('source1',), location=[0, 0])

        assert_raises(ValueError, bstream.transform_source_batch,
                      numpy.empty((5, 3, 4, 2)), 'source1')


class TestImage2DSlicer(ImageTestingMixin):
    def setUp(self):
        self.dataset = IndexableDataset(
            indexables=OrderedDict(
                [('images', numpy.random.randn(100, 1, 19, 19, 19)),
                 ('targets', numpy.random.randint(1, size=100))]))
        self.common_setup()

    def test_single_dimensions(self):
        # Illegal input
        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='xyz')
        assert_raises(ValueError, batch_stream.transform_source_batch,
                      numpy.random.randn(100, 1, 19, 19), 'images')

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='center',
                                     dimension_to_slice='xyz')
        assert_raises(ValueError, batch_stream.transform_source_batch,
                      numpy.random.randn(100, 1, 19, 19), 'images')

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='center',
                                     dimension_to_slice='z')

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert len(batch_shapes[0]) == 4

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='random',
                                     dimension_to_slice=0)

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert len(batch_shapes[0]) == 4

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='random',
                                     dimension_to_slice=1)

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert len(batch_shapes[0]) == 4

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='random',
                                     dimension_to_slice=2)

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert len(batch_shapes[0]) == 4

    def test_all_dimensions(self):
        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='center',
                                     dimension_to_slice=None,
                                     batch_or_channel=None)
        assert_raises(ValueError, batch_stream.transform_source_batch,
                      numpy.random.randn(100, 1, 19, 19), 'images')

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='center',
                                     dimension_to_slice=None,
                                     batch_or_channel='xyz')
        assert_raises(ValueError, batch_stream.transform_source_batch,
                      numpy.random.randn(100, 1, 19, 19), 'images')

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='center',
                                     dimension_to_slice=None,
                                     batch_or_channel=0)

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert batch_shapes[0][0] == 3 * self.batch_size

        batch_stream = Image2DSlicer(self.batch_stream,
                                     which_sources=('images',),
                                     slice_location='random',
                                     dimension_to_slice=None,
                                     batch_or_channel=1)

        batch_shapes = [batch[0].shape for batch
                        in batch_stream.get_epoch_iterator()]

        assert batch_shapes[0][1] == 3


class TestGammaCorrectionND(ImageTestingMixin):
    def setUp(self):
        self.rng = numpy.random.RandomState(123)
        self.source1 = self.rng.randn(100, 1, 19, 19, 19)
        axis_labels = {'source1': ('batch', 'channel', 'height', 'width'), }

        self.dataset = IndexableDataset(OrderedDict([('source1',
                                                      self.source1), ]),
                                        axis_labels=axis_labels)
        self.common_setup()
        self.gamma = 2.5
        self.transformer = GammaCorrectionND(self.batch_stream, self.gamma,
                                             which_sources=('source',))

    def test_gamma_correction(self):
        assert_equal(
            self.transformer.gamma_correction(self.source1, self.gamma),
            self.transformer.transform_source_batch(self.source1, 'source1'))

        cast = self.rng.binomial(1, .5, size=(100, 1, 19, 19, 19))
        source2 = 2 * (self.source1 - cast)

        def condition(array):
            return numpy.logical_and(array >= 1, array <= 0)

        assert_equal(condition(self.transformer.gamma_correction(source2,
                                                                 self.gamma)),
                     condition(source2))

    def test_batch_source_format(self):
        examples = [self.source1[i] for i in range(self.source1.shape[0])]
        expected_results = [self.transformer.gamma_correction(
            example, self.gamma) for example in examples]
        assert_equal(self.transformer.transform_source_batch(examples, 'any'),
                     expected_results)

        obj = numpy.empty(2, dtype=object)
        obj[0] = self.source1[0]
        obj[1] = self.source1[1]
        expected_results = numpy.array(
                         [self.transformer.transform_source_example(im, 'any')
                          for im in obj])
        assert_equal(self.transformer.transform_source_batch(obj, 'any'),
                     expected_results)

        wrong_format = [1, 2, 3, 4]
        assert_raises(ValueError, self.transformer.transform_source_batch,
                      wrong_format, 'any')
        assert_raises(ValueError, self.transformer.transform_source_example,
                      wrong_format, 'any')


class TestDrop(object):
    def setUp(self):
        self.sources = ['volume1', 'volume2', 'weight']
        self.which_weight = 'weight'
        self.im_shape = (10, 10)
        self.vo_shape = (10, 10, 10)

        self.data_im = {}
        self.data_vo = {}
        for k in range(len(self.sources)):
            self.data_im[self.sources[k]] = [0 for x in range(10)]
            self.data_vo[self.sources[k]] = [0 for x in range(10)]

        for k in range(10):
            self.data_im[self.sources[0]][k] = numpy.arange(
                numpy.prod(self.im_shape)).reshape(
                [1, 1] + list(self.im_shape)).astype(numpy.float32)
            self.data_vo[self.sources[0]][k] = numpy.arange(
                numpy.prod(self.vo_shape)).reshape(
                [1, 1] + list(self.vo_shape)).astype(numpy.float32)
            self.data_im[self.sources[1]][k] = numpy.arange(
                numpy.prod(self.im_shape)).reshape(
                [1, 1] + list(self.im_shape)).astype(numpy.float32)
            self.data_vo[self.sources[1]][k] = numpy.arange(
                numpy.prod(self.vo_shape)).reshape(
                [1, 1] + list(self.vo_shape)).astype(numpy.float32)
            self.data_im[self.sources[2]][k] = numpy.random.uniform(
                size=self.im_shape).reshape(
                [1, 1] + list(self.im_shape)).astype(numpy.float32)
            self.data_vo[self.sources[2]][k] = numpy.random.uniform(
                size=self.vo_shape).reshape(
                [1, 1] + list(self.vo_shape)).astype(numpy.float32)

        self.data = {}
        for type, data in zip(['image', 'volume'],
                              [self.data_im, self.data_vo]):
            self.data[type] = OrderedDict([('volume1', data[self.sources[0]]),
                                           ('volume2', data[self.sources[1]]),
                                           ('weight', data[self.sources[2]])])

        layout_im = ('batch', 'channel', 'width', 'height')
        layout_vol = ('batch', 'channel', 'x', 'y', 'z')
        self.axis_labels_im = {self.sources[0]: layout_im,
                               self.sources[1]: layout_im,
                               self.sources[2]: layout_im}
        self.axis_labels_vol = {self.sources[0]: layout_vol,
                                self.sources[1]: layout_vol,
                                self.sources[2]: layout_vol}

        self.stream = {}
        self.stream['image'] = DataStream(IterableDataset(
            self.data['image']), axis_labels=self.axis_labels_im)

        self.stream['volume'] = DataStream(IterableDataset(
            self.data['volume']), axis_labels=self.axis_labels_vol)
        self.dropstream = Drop(stream=self.stream['image'],
                               which_sources=('weight',))

    def test_init(self):
        # Illegal border
        kwargs = {'stream': self.stream['image'],
                  'which_sources': ('weight',),
                  'border': 'illegal'}
        assert_raises(TypeError, Drop, **kwargs)
        # Illegal dropout
        kwargs = {'stream': self.stream['image'],
                  'which_sources': ('weight',),
                  'dropout': 'illegal'}
        assert_raises(TypeError, Drop, **kwargs)

    def test_border_func(self):
        # Test illegal flag
        kwargs = {'volume': 0, 'border': 0, 'flag': 'iswearonmemum'}
        assert_raises(ValueError, self.dropstream._border_func, **kwargs)
        # Test uninterpretable number of dimensions
        kwargs = {'volume': numpy.asarray(0), 'border': 0, 'flag': 'source'}
        assert_raises(ValueError, self.dropstream._border_func, **kwargs)
        kwargs = {'volume': numpy.asarray(0), 'border': 0, 'flag': 'example'}
        assert_raises(ValueError, self.dropstream._border_func, **kwargs)
        # Test illegal border
        kwargs = {'volume': self.data_im['volume1'][0], 'border': 5,
                  'flag': 'source'}
        assert_raises(ValueError, self.dropstream._border_func, **kwargs)
        kwargs = {'volume': self.data_im['volume1'][0][0], 'border': 5,
                  'flag': 'example'}
        assert_raises(ValueError, self.dropstream._border_func, **kwargs)
        # Test border dropping for images
        # Source
        array = numpy.arange(5*5).reshape([1, 1, 5, 5])
        result = numpy.zeros([5, 5]).reshape([1, 1, 5, 5])
        result[:, :, 2, 2] = 12
        kwargs = {'volume': array, 'border': 2, 'flag': 'source'}
        assert numpy.allclose(result, self.dropstream._border_func(**kwargs))
        # Example
        array = numpy.arange(5*5).reshape([1, 5, 5])
        result = numpy.zeros([5, 5]).reshape([1, 5, 5])
        result[:, 2, 2] = 12
        kwargs = {'volume': array, 'border': 2, 'flag': 'example'}
        assert numpy.allclose(result, self.dropstream._border_func(**kwargs))
        # Test border dropping for volumes
        # Source
        array = numpy.arange(5*5*5).reshape([1, 1, 5, 5, 5])
        result = numpy.zeros([5, 5, 5]).reshape([1, 1, 5, 5, 5])
        result[:, :, 2, 2, 2] = 62
        kwargs = {'volume': array, 'border': 2, 'flag': 'source'}
        assert numpy.allclose(result, self.dropstream._border_func(**kwargs))
        # Example
        array = numpy.arange(5*5*5).reshape([1, 5, 5, 5])
        result = numpy.zeros([5, 5, 5]).reshape([1, 5, 5, 5])
        result[:, 2, 2, 2] = 62
        kwargs = {'volume': array, 'border': 2, 'flag': 'example'}
        assert numpy.allclose(result, self.dropstream._border_func(**kwargs))

    def test_dropout_func(self):
        rng = numpy.random.RandomState(123)
        array = numpy.arange(5*5).reshape([5, 5])
        result = array.copy()
        result[1, 1] = 0
        result[4, 1] = 0
        assert numpy.allclose(result, self.dropstream._dropout_func(array,
                                                                    0.2, rng))

    def test_transform_source_example(self):
        # Test illegal input
        kwargs = {'example': numpy.asarray(0), 'source_name': 'any'}
        assert_raises(ValueError, self.dropstream.transform_source_example,
                      **kwargs)
        # No transformation
        array = numpy.arange(5*5*5).reshape([1, 5, 5, 5])
        kwargs = {'example': array, 'source_name': 'any'}
        assert numpy.allclose(self.dropstream.transform_source_example(
            array, 'any'), array)
        # Border drop
        dropstream = Drop(stream=self.stream['image'],
                          which_sources=('weight',),
                          border=2)
        result = numpy.zeros([5, 5, 5]).reshape([1, 5, 5, 5])
        result[:, 2, 2, 2] = 62
        assert numpy.allclose(dropstream.transform_source_example(
            array, 'any'), result)
        # Dropout
        rng = numpy.random.RandomState(123)
        array = numpy.arange(5*5).reshape([1, 5, 5])
        result = array.copy()
        result[:, 1, 1] = 0
        result[:, 4, 1] = 0
        kwargs = {'rng': rng}
        dropstream = Drop(stream=self.stream['image'],
                          which_sources=('weight',),
                          dropout=0.2, **kwargs)
        assert numpy.allclose(result,
                              dropstream.transform_source_example(
                                  array, 'any'))

    def test_transform_source_batch(self):
        # Test illegal source input
        kwargs = {'source': numpy.asarray(0), 'source_name': 'any'}
        assert_raises(ValueError, self.dropstream.transform_source_batch,
                      **kwargs)
        # Test batch
        # No transformation
        array = numpy.arange(5*5*5).reshape([1, 1, 5, 5, 5])
        kwargs = {'source': array, 'source_name': 'any'}
        assert numpy.allclose(self.dropstream.transform_source_batch(
            array, 'any'), array)
        # Border drop
        dropstream = Drop(stream=self.stream['image'],
                          which_sources=('weight',),
                          border=2)
        result = numpy.zeros([5, 5, 5]).reshape([1, 1, 5, 5, 5])
        result[:, :, 2, 2, 2] = 62
        assert numpy.allclose(dropstream.transform_source_batch(array, 'any'),
                              result)
        # Dropout
        rng = numpy.random.RandomState(123)
        array = numpy.arange(5*5).reshape([1, 1, 5, 5])
        result = array.copy()
        result[:, :, 1, 1] = 0
        result[:, :, 4, 1] = 0
        kwargs = {'rng': rng}
        dropstream = Drop(stream=self.stream['image'],
                          which_sources=('weight',),
                          dropout=0.2, **kwargs)
        assert numpy.allclose(result,
                              dropstream.transform_source_batch(array, 'any'))
