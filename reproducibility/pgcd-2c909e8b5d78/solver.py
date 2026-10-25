"""Scalar angular spectrum propagation with a conservative bandlimit.

Model: monochromatic scalar field in homogeneous free space; thin ideal lens;
no nonlinear optics, polarization, SLM calibration, aberrations or hardware.

References:
  Matsushima & Shimobaba, Optics Express 17, 19662 (2009),
  https://doi.org/10.1364/OE.17.019662

The radial cutoff used here is conservative and not a full implementation of
all passbands in the original band-limited ASM publication.
"""
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class OpticalSetup:
    n: int = 256
    extent_m: float = 2.4e-3
    wavelength_m: float = 633e-9
    waist_m: float = 0.30e-3
    focal_length_m: float = 0.060
    power_w: float = 1.0

    def __post_init__(self):
        if self.n <= 32 or self.n % 2:
            raise ValueError('n must be an even integer > 32')
        if min(self.extent_m, self.wavelength_m, self.waist_m,
               self.focal_length_m, self.power_w) <= 0:
            raise ValueError('All physical parameters must be positive')
        if self.waist_m * 6 >= self.extent_m:
            raise ValueError('Gaussian waist must be comfortably inside the window')


class AngularSpectrum:
    def __init__(self, setup: OpticalSetup, z_m, *, backend="numpy", gpu_memory_mb=512):
        if backend not in ('numpy', 'cuda'):
            raise ValueError('backend must be numpy or cuda')
        self.backend = backend
        self.gpu_memory_mb = gpu_memory_mb
        self.xp = np
        if backend == 'cuda':
            try:
                import cupy as cp
                if cp.cuda.runtime.getDeviceCount() < 1:
                    raise RuntimeError('No CUDA device found')
                cp.zeros(1).sum().item()
                self.xp = cp
            except Exception as exc:
                raise RuntimeError('CUDA requested but unavailable; install compatible CuPy/CUDA. No CPU fallback.') from exc
        self.setup = setup
        self.z_m = np.asarray(z_m, dtype=float)
        if self.z_m.ndim != 1 or len(self.z_m) < 2 or np.any(self.z_m < 0):
            raise ValueError('z_m must contain >= 2 nonnegative propagation distances')
        n = setup.n
        # Conservative array/FFT workspace estimate; not a hard allocator cap.
        if backend == 'cuda':
            required = n*n*(len(self.z_m)*40 + 256)
            free, _ = self.xp.cuda.runtime.memGetInfo()
            if gpu_memory_mb <= 0 or required > min(gpu_memory_mb*1024**2, free*0.8):
                raise MemoryError('Estimated GPU working set exceeds configured budget or free memory')
        self.dx = setup.extent_m / n
        coord = (np.arange(n) - n // 2) * self.dx
        self.x, self.y = np.meshgrid(coord, coord)
        self.r2 = self.x**2 + self.y**2
        freq = np.fft.fftfreq(n, d=self.dx)
        fx, fy = np.meshgrid(freq, freq)
        self.f2 = fx**2 + fy**2
        lam = setup.wavelength_m
        # Remove evanescent spectrum. This MVP does not analyze nanoscale near fields.
        kz = 2 * np.pi * np.sqrt(np.maximum(0., 1. / lam**2 - self.f2))
        bands = []
        kernels = []
        # DFT phase factor for reading the spatial pixel (n//2,n//2).
        idx = np.arange(n)
        sign = (1. - 2. * (idx % 2)).astype(np.float64)
        center_phase = np.outer(sign, sign) / (n * n)
        for z in self.z_m:
            # Radial conservative anti-aliasing cutoff derived from phase gradient.
            fcut = (1. / lam) / np.sqrt(1. + (2. * z / setup.extent_m)**2)
            band = (self.f2 <= fcut**2) & (self.f2 <= 1. / lam**2)
            bands.append(band)
            kernels.append(np.exp(1j * z * kz) * band)
        self.bands = np.asarray(bands)
        self.kernels = np.asarray(kernels)
        self.center_kernels = self.kernels * center_phase
        amp = np.exp(-self.r2 / setup.waist_m**2)
        amp = amp / np.sqrt(np.sum(np.abs(amp)**2) * self.dx**2)
        self.amplitude = np.sqrt(setup.power_w) * amp
        self.lens_phase = -(2 * np.pi / lam) * self.r2 / (2 * setup.focal_length_m)

        self._device_kernels = self.xp.asarray(self.kernels)
        self._device_center = self.xp.asarray(self.center_kernels)
        self._device_bands = self.xp.asarray(self.bands, dtype=float)
        self._device_amplitude = self.xp.asarray(self.amplitude)
        self._device_lens = self.xp.asarray(self.lens_phase)

    def to_host(self, value):
        return self.xp.asnumpy(value) if self.backend == 'cuda' else np.asarray(value)

    def fft2(self, field):
        return self.xp.fft.fft2(self.xp.asarray(field), axes=(-2, -1))

    def input_field(self, residual_phase=0.0):
        return self.amplitude * np.exp(1j * (self.lens_phase + residual_phase))

    def center_trace_from_spectrum(self, spectrum):
        # Equivalent to ifft2(spectrum * kernel)[n//2,n//2] for each z.
        center = self.xp.einsum('ij,zij->z', self.xp.asarray(spectrum), self._device_center, optimize=False)
        return self.to_host(self.xp.abs(center)**2)

    def center_trace(self, residual_phase=0.0):
        field = self._device_amplitude * self.xp.exp(1j * (self._device_lens + self.xp.asarray(residual_phase)))
        return self.center_trace_from_spectrum(self.fft2(field))

    def field(self, spectrum, z_index):
        return self.to_host(self.xp.fft.ifft2(self.xp.asarray(spectrum) * self._device_kernels[z_index]))

    def input_spectral_retention(self, spectrum):
        power_spec = self.xp.abs(self.xp.asarray(spectrum))**2
        retained = self.xp.einsum('ij,zij->z', power_spec, self._device_bands)
        return self.to_host(retained / power_spec.sum())

    def edge_fraction(self, field, edge_frac=0.12):
        intensity = np.abs(field)**2
        a = int(round(self.setup.n * edge_frac))
        center = intensity[a:-a, a:-a].sum()
        return float(1. - center / intensity.sum())

    def encircled_fraction(self, field, radius_m=110e-6):
        intensity = np.abs(field)**2
        return float(intensity[self.r2 <= radius_m**2].sum() / intensity.sum())


def fresnel_direct(field,sim,z,x_out=None):
    """Independent separable real-space Fresnel quadrature (not an ASM FFT).

    U=e^(ikz)/(i*lambda*z) integral U0 exp[ik*((x-x')²+(y-y')²)/(2z)] dx'dy'.
    The paraxial model must agree only in its applicable low-angle regime.
    CUDA uses explicit CuPy matrix products; CPU is an explicit backend choice.
    """
    if z<=0:raise ValueError('Direct Fresnel requires z>0')
    xp=sim.xp
    xin=xp.asarray(sim.x[0])
    output=xin if x_out is None else xp.asarray(x_out)
    k=2*np.pi/sim.setup.wavelength_m
    matrix=xp.exp(1j*k/(2*z)*(output[:,None]-xin[None,:])**2)
    result=np.exp(1j*k*z)/(1j*sim.setup.wavelength_m*z)*sim.dx**2*(matrix@xp.asarray(field)@matrix.T)
    return sim.to_host(result)
