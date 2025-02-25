import numpy as np
import xarray as xr

import brainscore
from brainscore.benchmarks import BenchmarkBase
from brainscore.benchmarks.imagenet import NUMBER_OF_TRIALS
from brainscore.metrics import Score
from brainscore.metrics.accuracy import Accuracy
from brainscore.model_interface import BrainModel

BIBTEX = """@ARTICLE{Hendrycks2019-di,
   title         = "Benchmarking Neural Network Robustness to Common Corruptions
                    and Perturbations",
   author        = "Hendrycks, Dan and Dietterich, Thomas",
   abstract      = "In this paper we establish rigorous benchmarks for image
                    classifier robustness. Our first benchmark, ImageNet-C,
                    standardizes and expands the corruption robustness topic,
                    while showing which classifiers are preferable in
                    safety-critical applications. Then we propose a new dataset
                    called ImageNet-P which enables researchers to benchmark a
                    classifier's robustness to common perturbations. Unlike
                    recent robustness research, this benchmark evaluates
                    performance on common corruptions and perturbations not
                    worst-case adversarial perturbations. We find that there are
                    negligible changes in relative corruption robustness from
                    AlexNet classifiers to ResNet classifiers. Afterward we
                    discover ways to enhance corruption and perturbation
                    robustness. We even find that a bypassed adversarial defense
                    provides substantial common perturbation robustness.
                    Together our benchmarks may aid future work toward networks
                    that robustly generalize.",
   month         =  mar,
   year          =  2019,
   archivePrefix = "arXiv",
   primaryClass  = "cs.LG",
   eprint        = "1903.12261",
   url           = "https://arxiv.org/abs/1903.12261"
}"""


def Imagenet_C_Noise(sampling_factor=10):
    return Imagenet_C_Category('noise', sampling_factor=sampling_factor)


def Imagenet_C_Blur(sampling_factor=10):
    return Imagenet_C_Category('blur', sampling_factor=sampling_factor)


def Imagenet_C_Weather(sampling_factor=10):
    return Imagenet_C_Category('weather', sampling_factor=sampling_factor)


def Imagenet_C_Digital(sampling_factor=10):
    return Imagenet_C_Category('digital', sampling_factor=sampling_factor)


class Imagenet_C_Category(BenchmarkBase):
    """
    Runs all ImageNet C benchmarks within a noise category, ie: 
    gaussian noise [1-5]
    shot noise [1-5]
    impulse noise [1-5]
    """
    noise_category_map = {
        'noise': ['gaussian_noise', 'shot_noise', 'impulse_noise'],
        'blur': ['glass_blur', 'motion_blur', 'zoom_blur', 'defocus_blur'],
        'weather': ['snow', 'frost', 'fog', 'brightness'],
        'digital': ['pixelate', 'contrast', 'elastic_transform', 'jpeg_compression']
    }

    def __init__(self, noise_category, sampling_factor=10):
        self.noise_category = noise_category
        self.stimulus_set_name = f'dietterich.Hendrycks2019.{noise_category}'

        # take every nth image, n=sampling_factor.
        stimulus_set = brainscore.get_stimulus_set(self.stimulus_set_name)[::sampling_factor]
        self.stimulus_set = stimulus_set
        self.noise_types = self.noise_category_map[noise_category]

        ceiling = Score([1, np.nan], coords={'aggregation': ['center', 'error']}, dims=['aggregation'])
        super(Imagenet_C_Category, self).__init__(identifier=f'dietterich.Hendrycks2019-{noise_category}-top1',
                                                  version=2,
                                                  ceiling_func=lambda: ceiling,
                                                  parent='dietterich.Hendrycks2019-top1',
                                                  bibtex=BIBTEX)

    def __call__(self, candidate):
        scores = xr.concat([
            Imagenet_C_Type(self.stimulus_set, noise_type, self.noise_category)(candidate)
            for noise_type in self.noise_types
        ], dim='presentation')
        assert len(set(scores['noise_type'].values)) == len(self.noise_types)
        center = np.mean(scores)
        error = np.std(scores)
        score = Score([center, error], coords={'aggregation': ['center', 'error']}, dims=('aggregation',))
        score.attrs[Score.RAW_VALUES_KEY] = scores
        return score


class Imagenet_C_Type(BenchmarkBase):
    """
    Runs a group in imnet C benchmarks, like gaussian noise [1-5]
    """

    def __init__(self, stimulus_set, noise_type, noise_category):
        self.stimulus_set = stimulus_set[stimulus_set['noise_type'] == noise_type]
        self.noise_type = noise_type
        self.noise_category = noise_category
        ceiling = Score([1, np.nan], coords={'aggregation': ['center', 'error']}, dims=['aggregation'])
        super(Imagenet_C_Type, self).__init__(identifier=f'dietterich.Hendrycks2019-{noise_category}-{noise_type}-top1',
                                              version=2,
                                              ceiling_func=lambda: ceiling,
                                              parent=f'dietterich.Hendrycks2019-{noise_category}-top1',
                                              bibtex=BIBTEX)

    def __call__(self, candidate):
        score = xr.concat([
            Imagenet_C_Individual(self.stimulus_set, noise_level, self.noise_type, self.noise_category)(candidate)
            for noise_level in range(1, 6)
        ], dim='presentation')
        return score


class Imagenet_C_Individual(BenchmarkBase):
    """
    Runs an individual ImageNet C benchmark, like "gaussian_noise_1"
    """

    def __init__(self, stimulus_set, noise_level, noise_type, noise_category):
        self.stimulus_set = stimulus_set[stimulus_set['noise_level'] == noise_level]
        self.noise_level = noise_level
        self.noise_type = noise_type
        self.benchmark_name = f'dietterich.Hendrycks2019-{noise_category}-{noise_type}-{noise_level}-top1'
        self._similarity_metric = Accuracy()
        ceiling = Score([1, np.nan], coords={'aggregation': ['center', 'error']}, dims=['aggregation'])
        super(Imagenet_C_Individual, self).__init__(identifier=self.benchmark_name, version=2,
                                                    ceiling_func=lambda: ceiling,
                                                    parent=f'dietterich.Hendrycks2019-{noise_category}-{noise_type}-top1',
                                                    bibtex=BIBTEX)

    def __call__(self, candidate):
        candidate.start_task(BrainModel.Task.label, 'imagenet')
        stimulus_set = self.stimulus_set[
            list(set(self.stimulus_set.columns) - {'synset'})].copy().reset_index()  # do not show label
        stimulus_set.identifier = f'{self.benchmark_name}-{len(stimulus_set)}samples'
        predictions = candidate.look_at(stimulus_set, number_of_trials=NUMBER_OF_TRIALS)
        score = self._similarity_metric(
            predictions.sortby('filename'),
            self.stimulus_set.sort_values('filename')['synset'].values
        ).raw

        score = score.assign_coords(
            name=('presentation', [f'{self.benchmark_name}' for _ in range(len(score.presentation))])
        )

        return score
