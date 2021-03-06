

import numpy as np

# these values are given in the paper but probably can be changed
WEIGHT = 1e-4 # threshold weight
M = 0.1 # chance of survival for roulette
COSZERO = 1.0 - 1.0e-12 # limit used to determine nearly normal incidence
                        # measured from z-axis
COS90 = 1.0e-6 # limit used to determine nearly parallel incidence
PARTIAL_REFLECTION = 0 # pick zero for OFF, one for ON
# PULSE = 0 # arterial pulse -- pick zero for DIASTOLE, one for SYSTOLE
 
class medium:
    """
    medium class defining the optical properties of a medium
    for a given wavelength lambda.

        name: the name of the medium
        n: refractive index
        g: anisotropy
        z: thickness of layer of medium (along z-axis)
        mua: absorption coefficient [1/cm]
        mus: scattering coefficient [1/cm]
    """
    def __init__(self, name, n, g, z, mua, mus):
        self.name = name
        self.n = n
        self.mua = mua
        self.mus = mus
        self.g = g
        self.z = z

class skin:
    def __init__(self, name, n, g, z, Vb, Vw, p, wavelength, ds):
        self.name = name
        self.n = n
        self.g = g
        self.z = z
        self.percentOxy = p
        if ds.lower() == "diastole".lower():
            self.Vb = Vb
            self.vVen = 0.75*Vb
            self.vArt = self.Vb-self.vVen
        else:
            self.Vb = 1.25*Vb
            self.vVen = 0.75*Vb
            self.vArt = self.Vb-self.vVen
        self.Vw = Vw
        self.wavelength = wavelength
        if self.wavelength == 660:
            self.muaHbO2 = 0.15 # muaHbO2 [1/mm]
            self.muaHb = 1.64 # musHbO2 [1/mm]
            self.musHbO2 = 87.61 # muaHb [1/mm]
            self.musHb = 81.45 # musHb [1/mm]
            self.mus = 25.62 # from paper
            self.muaw = 0.0036
        elif self.wavelength == 940: # infrared
            self.muaHbO2 = 0.65 # muaHbO2 [1/mm]
            self.muaHb = 0.43 # musHbO2 [1/mm]
            self.musHbO2 = 66.08 # muaHb [1/mm]
            self.musHb = 49.66 # musHb [1/mm]
            self.mus = 15.68 # from paper
            self.muaw = 0.2674
        self.mua = self.calcMua()
    
    def calcMua(self):
        SaO2 = self.percentOxy
        if self.percentOxy == 0.0:
            SvO2 = 0.0
        else:
            SvO2 = self.percentOxy-0.1 # 10% lower than arterial oxygenation
        muaHbO2 = self.muaHbO2
        muaHb = self.muaHb
        vArt = self.vArt # need to change this    # ratio art:ven is 1:1
        vVen = self.vVen # need to change this
        vWat = self.Vw
        vMel = 0.1 # fraction of melanin
        watMua = self.muaw
        # set baseline mua
        lam = self.wavelength
        muab = (7.84e7)*lam**(-3.255) # baseline
        artMua = SaO2*muaHbO2 + (1.0-SaO2)*muaHb # arterial absorption 
        venMua = SvO2*muaHbO2 + (1.0-SvO2)*muaHb # venous absorption
        # absorption coefficient (layer dependent)
        if self.name == "epidermis" \
            or self.name == "stratum corneum": # epidermis has no blood,
            melMua = (6.6e10)*lam**(-3.33)       # but does have melanin
            mua = vMel*melMua + vWat*watMua + (1.0 - (vMel + vWat))*muab
        else:
            mua = vArt*artMua + vVen*venMua + vWat*watMua + \
                        (1.0 - (vArt + vVen + vWat))*muab
        return mua

class Fat:
    def __init__(self,name, n, g, z, wavelength):
        self.name = name
        self.n = n
        self.g = g
        self.z = z
        self.wavelength = wavelength
        if self.wavelength == 660:
            self.mua = 0.0104
            self.mus = 6.20
        else:
            self.mua = 0.017
            self.mus = 5.42

class Muscle:
    def __init__(self,name, n, g, z, wavelength):
        self.name = name
        self.n = n
        self.g = g
        self.z = z
        self.nBone = 2.0 # refractive index of bone (guess, need to check)
        self.wavelength = wavelength
        if self.wavelength == 660:
            self.mua = 0.0816
            self.mus = 8.61
            self.muaBone = 0.0351 # absorption coefficient of bone [1/mm]
            self.musBone = 34.45 # scattering coefficient of bone [1/mm]
        else:
            self.mua = 0.0401
            self.mus = 5.81
            self.muaBone = 0.0457
            self.musBone = 24.70
        self.gBone = 0.092 # anisotropy of bone
        self.rBone = 2.0 # radius of bone [mm]
        self.boneCenter = [0, 0, 6.5] # from skin surface [mm]

class model:
    """
    monte carlo multi-layer (MCML) simulation for a given tissue structure.
    rather than separate input and output into two distinct classes (as is
    done in the paper), this class contains the entire model

    these variables (input) are used for defining the model--
        layers: layer structure of tissue
        layerDepth: top and bottom depth of each tissue in z direction [cm]
        W_th: theshold weight for roulette
        cosCrit: ciritical angle cosines of each layer (top and bottom)
                    used for Fresnel equations
        dz: z grid separation [cm]
        dr: r grid separation [cm]
        da: alpha grid separation [rad]
        nz: number of array elements
        nr: number of array elements
        na: number of array elements
    
    these variables (output) are used for storing the simulation data--
        numberOfPhotons: number of photons
        Rsp: specular reflectance
        Rd: total diffuse reflectance
        A: total absorption probability
        Tt: total transmittance
        Rd_ra: 2D distribution of diffuse reflectance [1/(cm**2 sr)]
        Rd_r: 1D radial distribution of diffuse reflectance [1/cm**2]
        Rd_a: 1D angular distribution of diffuse reflectance [1/sr]
        A_rz: 2D probability density over r & z [1/cm**3]
        A_z: 1D probability density over z [1/cm]
        A_l: each layer's absorption probability
        Phi_rz: fluence [1/cm**2]
        Phi_z: 1D probability density over z of fluence [-]
        Tt_ra: 2D distribution of total transmittance [1/(cm**2 sr)]
        Tt_r: 1D radial distribution of transmittance [1/cm**2]
        Tt_a: 1D angular distribution of transmittance [1/sr]
    """
    def __init__(self, structure, numberOfLayers):
        self.layers = structure # structure = mediumStructure, i.e. a list
                                # of medium objects
        self.numberOfLayers = numberOfLayers
        # find depths of each layers
        z = 0 # 'top' or 'surface' of tissue
        self.layerDepth = []
        self.layerDepth.append([0,0]) # skip air layer
        for i in range(1, self.numberOfLayers+1):
            self.layerDepth.append([z, z+self.layers[i].z]) # the first
                                                   # coordinate is the top of
                                                   # a layer and second
                                                   # coordinate is the bottom
            z+=self.layers[i].z
        self.W_th = WEIGHT
        self.cosCrit = []
        self.cosCrit.append([0,0])
        for i in range(1, self.numberOfLayers+1):
            # calculate the cosine of the critical angles for each layer
                    # these will be used later for determining
                    # whether a photon is reflected internally
                    # or transmitted to a new layer after hitting a boundary
            
            # crticial angle at top interface of the current layer
            n_i = self.layers[i].n
            n_t = self.layers[i-1].n
            if n_i >= n_t:
                cosCritTop = ( 1.0 - (n_t**2.0)/(n_i**2.0) )**0.5
            else:
                cosCritTop = 0.0 # set to zero if 
                                # no internal reflection exists
            # crticial angle at bottom interface of the current layer
            n_t = self.layers[i+1].n
            if n_i >= n_t:
                cosCritBott = ( 1.0 - (n_t**2.0)/(n_i**2.0) )**0.5
            else:
                cosCritBott = 0.0 # set to zero if 
                                # no internal reflection exists
            self.cosCrit.append([cosCritTop, cosCritBott])
        # generate grid and step size 
        self.nx = 650
        self.ny = 650
        self.nz = 650 # with dz = 2e-2, gives total thickness of 13mm
        self.nr = 250 # with dr = 2e-2, gives diameter of 5mm
        self.na = 30
        self.dx = 2e-2
        self.dy = 2e-2
        self.dz = 2e-2 # [mm]
        self.dr = 2e-2 # [mm]
        self.da = 0.5*(np.pi)/(self.na)
        # initial photons sent through simulation
        self.numberOfPhotons = 0
        # initialize the model grid arrays  
        self.Rsp = self.calcSpecular()
        self.Rd = 0.0
        self.A = 0.0
        self.Tt = 0.0
        # self.Rd_xyz = np.zeros((self.nz,self.ny,self.nz))
        self.Rd_ra = np.zeros((self.nr, self.na))
        self.Rd_r = np.zeros(self.nr)
        self.Rd_a = np.zeros(self.na)
        # self.A_xyz = np.zeros((self.nz,self.ny,self.nz))
        self.A_rz = np.zeros((self.nr, self.nz))
        self.A_z = np.zeros(self.nz)
        self.A_l = np.zeros(numberOfLayers+2)
        # self.Phi_xyz = np.zeros((self.nz,self.ny,self.nz))
        self.Phi_rz = np.zeros((self.nr, self.nz))
        self.Phi_z = np.zeros(self.nz)
        # self.Tt_xyz = np.zeros((self.nz,self.ny,self.nz))
        self.Tt_ra = np.zeros((self.nr, self.na))
        self.Tt_r = np.zeros(self.nr)
        self.Tt_a = np.zeros(self.na)
    
    def run(self, photonsToLaunch):
        for i in range(photonsToLaunch):
            self.numberOfPhotons+=1
            photon = Photon(self)
            photon.launchPhoton(self)
    
    # calculate specular intial reflection at first tissue layer only
    # assume reflections inside tissue are diffuse
    def calcSpecular(self):
        # direct reflections from the 1st and 2nd layers.
        r1 = ( (self.layers[0].n - self.layers[1].n) / \
              (self.layers[0].n + self.layers[1].n) )**2 
        # if first layer is glass (or another clear medium)
        if ((self.layers[1].mua == 0.0) and (self.layers[1].mus == 0.0)):
            r2 = ((self.layers[1].n - self.layers[2].n)/(self.layers[1].n + \
                self.layers[2].n))**2
            r1 = r1 + ( ((1 - r1)**2) * r2 ) / (1 - r1*r2) 
        return r1
    
# need to sum the transmittance, reflectance, absorption arrays still
# also scale the arrays
    
    def computeAndScaleArraySums(self):
        """
        compute 1D and scalar array sums
        
        also scale reflectance and transmittance arrays
        """
        self.sumRT()
        self.scaleRT()
        self.sumA()
        self.scaleA()
        self.Fluence()
        
        
    def sumRT(self):
        # sum 2D arrays to get radial and angular probilities
        
        # radial arrays
        for ir in range(self.nr):
            sumR = 0.0
            sumT = 0.0
            for ia in range(self.na):
                sumR += self.Rd_ra[ir, ia]
                sumT += self.Tt_ra[ir, ia]
            self.Rd_r[ir] = sumR
            self.Tt_r[ir] = sumT
        
        # angular arrays
        for ia in range(self.na):
            sumR = 0.0
            sumT = 0.0
            for ir in range(self.nr):
                sumR += self.Rd_ra[ir, ia]
                sumT += self.Tt_ra[ir, ia]
            self.Rd_a[ia] = sumR
            self.Tt_a[ia] = sumT
        
        # scalars
        sumR = 0.0
        sumT = 0.0
        for ir in range(self.nr):
            sumR += self.Rd_r[ir]
            sumT += self.Tt_r[ir]
        self.Rd = sumR
        self.Tt = sumT                       
    
    def sumA(self):
        # sum 2D arrays to get radial and angular probilities
        
        # z array
        for iz in range(self.nz):
            sumA = 0.0
            for ir in range(self.nr):
                sumA += self.A_rz[ir, iz]
            self.A_z[iz] = sumA
        
        # layer array
        sumA = 0.0
        for iz in range(self.nz):
            sumA += self.A_z[iz]
            self.A_l[self.indexLayer(iz)] += self.A_z[iz]

        self.A = sumA
        
    def indexLayer(self, iz):
        # find the index to the layer according to the index
        # to the grid system in z direction

        i = 1     	# index to layer.
        while (iz+0.5)*self.dz >= self.layerDepth[i][1] and \
               i < self.numberOfLayers:
                   i += 1
        return i
    
    def Fluence(self):
        for iz in range(self.nz):
            for ir in range(self.nr):
                mua = self.muaIz(iz)
                self.Phi_rz[ir,iz] = self.A_rz[ir,iz]/mua # since A_rz, A_r,
                self.Phi_z[iz] = self.A_z[iz]/mua       # and A_z have been
                                                      # scaled, phi arrays
                                                      # should also be scaled
    
    def muaIz(self, iz):
        # get mua at a given index iz
        i = 1       # index to layer
        nLayers = self.numberOfLayers
        dz = self.dz
        while ((iz + 0.5)*dz >= self.layerDepth[i][1] \
               and i < nLayers):
            i += 1
        mua = self.layers[i].mua
        return mua
    
    def scaleRT(self):
        # scale Rd and Tt array
        # more info given in paper.  too complicated to put here
        # dSolidAngle = 4.0*pi*sin[(ia + 0.5)*da]*sin[0.5*da]
        # dArea = 2.0*pi*(ir+0.5)*(dr**2.0)

        # scale 2D arrays
        # dArea*cos(a)*dSolidAngle*numberOfPhotons
        for ir in range(self.nr):  
            for ia in range(self.na):
                dArea = 2.0*np.pi*(ir+0.5)*(self.dr**2.0)
                dSolidAngle = 4.0*np.pi*\
                                np.sin((ia + 0.5)*self.da)*np.sin(0.5*self.da)
                scale = dArea*np.cos((ia+0.5)*self.da)*\
                    dSolidAngle*self.numberOfPhotons
                self.Rd_ra[ir, ia] /= scale
                self.Tt_ra[ir, ia] /= scale
        
        # scale radial arrays
        # divide by dArea*numberOfPhotons
        for ir in range(self.nr):
            dArea = 2.0*np.pi*(ir+0.5)*(self.dr**2.0)
            scale = (dArea*self.numberOfPhotons)
            self.Rd_r[ir] /= scale
            self.Tt_r[ir] /= scale
        
        # scale angular arrays
        # divide by dSolidAngle*numberOfPhoton
        for ia in range(self.na):
            dSolidAngle = 4.0*np.pi*\
                                np.sin((ia + 0.5)*self.da)*\
                                    np.sin(0.5*self.da)
            scale = dSolidAngle*self.numberOfPhotons
            self.Rd_a[ia] /= scale
            self.Tt_a[ia] /= scale
        
        # scale scalars
        # divide by number of photons
        scale = self.numberOfPhotons
        self.Rd /= scale
        self.Tt /= scale
    
    def scaleA(self):
        # scale A_rz
        for iz in range(self.nz):
            for ir in range(self.nr):
                dArea = 2.0*np.pi*(ir+0.5)*(self.dr**2.0)
                scale = (dArea*self.dz*self.numberOfPhotons)
                self.A_rz[ir, iz] /= scale
  
        # scale A_z
        scale = (self.dz*self.numberOfPhotons)
        for iz in range(self.nz):
            self.A_z[iz] /= scale
  
        # scale A_l
        scale = self.numberOfPhotons	
        for il in range(self.numberOfLayers+2):
            self.A_l[il] /= scale
        
        # scale A
        self.A /=scale  

class Photon:
    """
    photon class for monte carlo scattering model. the z-axis is directed
    'down' so positve uz represents a photon moving down while negative
    uz represents a photon moving up.
    
        x: Cartesian coordinate x [cm]
        y: Cartesian coordinate y [cm]
        z: Cartesian coordinate z [cm]
        ux: directional cosine x of a photon
        uy: directional cosine y of a photon
        uz: directional cosine z of a photon
        w: current weight of photon
        dead: true if photon is terminated
        layer: index to layer where the photon packet resides
        s: current step size [cm]
        s_rem: step size remaining after hitting a boundary [-]           
    """        
    def __init__(self, model):
        self.x = 0.0
        self.y = 0.0
        self.z = 0.0
        # if the first layer is glass
        if (model.layers[1].mua == 0.0) \
            and (model.layers[1].mus == 0.0):
                self.layer = 2      # skip to next layer
                self.z = model.layerDepth[2][0]  # use z0 from the 
                                                       # next layer
        self.ux = 0.0
        self.uy = 0.0
        self.uz = 1.0
        self.w = 1.0 - model.Rsp # photon weight initialized at
                        # unity with specular reflectance subtracted off
        self.dead = False
        self.layer = 1 # current layer # skip air
        self.s = 0
        self.s_rem = 0
    
    # launch a photon to begin simulation
    def launchPhoton(self, model):
        while self.dead == False:
            if (model.layers[self.layer].mua == 0) \
                and (model.layers[self.layer].mus == 0): # check for glass 
                    self.hopDropSpinGlass(model)
            else:
                self.hopDropSpinTissue(model)
                # once photon weight is below the theshold weight,
                # play roulette to see if photon dies or not
            if self.dead == False and self.w < model.W_th:
                self.roulette()
    
    def roulette(self):
        """
        once the photon's weight drops below a certain theshold weight W_th,
        play roulette to see if it 'lives' or 'dies'
        """
        if self.w == 0.0:	# photon is dead by definition
            self.dead = True
        elif np.random.random_sample() < M: # photon lives
            self.w /= M
        else: # photon dies
            self.dead = True
   
    def hopDropSpinGlass(self, model):
        # move the photon packet in glass layer.
        # horizontal photons 'die' because they will
        # never interact with tissue
        if self.uz == 0:
            # horizontal photon in glass is killed
            self.dead = True
        else:
            self.stepSizeGlass(model)
            self.hop() # only hop since mua = mus = 0 implies no
                       # drop (absorption) or spin (scattering)
            self.newLayerCheck(model)
    
    def stepSizeGlass(self, model):
        # photon moves uninterrupted through glass (no drop/spin), so
        # s = d_b, where d_b is distance to boundary
        layer = self.layer
        z = self.z
        uz = self.uz
        if uz > 0.0: # photon moving down
            d_b = (model.layerDepth[layer][1] - z)/uz
        else: # photon moving up
            d_b = (model.layerDepth[layer][0] - z)/uz
        self.s = d_b
    
    def newLayerCheck(self, model):
        """
        when a boundary is hit, this function determines whether a photon
        is reflected internally or transmitted to a new layer
        (perhaps partially)
        """
        uz = self.uz
        r = 0.0
        if uz < 0.0: # photon moving up
            # refractive indices
            n_i = model.layers[self.layer].n # current layer
            n_t = model.layers[self.layer-1].n # new layer
            
            # determine reflectance r
            if (abs(uz) <= model.cosCrit[self.layer][0]): 
                # it can be shown that uz <= cosCrit is the same
                # requirement as angleInc => angleCrit. this method is more
                # efficient than using trig functions
                r = 1.0 # total internal reflection
            else:
                r, uzNew = self.calcFresnel(n_i, n_t, abs(uz))
            # photon may be partially reflected and partially transmitted
            # instad of pure reflection and transmission at tissue surface
            if PARTIAL_REFLECTION == 1:
                if self.layer == 1 and r < 1.0: # if it's the first layer and
                                                # partial reflection,
                                                # some of photon can be
                                                # leave tissue (die)
                    self.uz = -uzNew # the part that is transmitted (dead)
                    self.recordReduce(model,r) # record what leaves and update the
                        # photon's weight. note: transmission through the first
                        # layer is the same as reflection off of the top layer,
                        # which is why the function here records reflectance R
                    self.uz = -uz # the part that is reflected internally (alive)
                elif np.random.random() > r: # transmitted to layer-1
                    self.layer-=1
                    self.ux *= n_i/n_t
                    self.uy *= n_i/n_t
                    self.uz = -uzNew
                else:
                    self.uz = -uz # internally reflected
            # can't get partial reflection to work, so use this
            else:
                if np.random.random() > r:   # transmitted out
                    if self.layer == 1:
                        self.uz = -uzNew
                        self.recordReduce(model, 0.0)
                        self.dead = True
                    else: # transmitted to layer-1
                        self.layer -= 1
                        self.ux *= n_i/n_t
                        self.uy *= n_i/n_t
                        self.uz = -uzNew
                else: 						# reflected
                    self.uz = -uz
        
        else: #photon moving down
            # refractive indices
            n_i = model.layers[self.layer].n # current layer
            n_t = model.layers[self.layer+1].n # new layer
            # determine reflectance r
            if (abs(uz) <= model.cosCrit[self.layer][1]): 
                r = 1.0 # total internal reflection
            else:
                r, uzNew = self.calcFresnel(n_i, n_t, uz)
            # determine if photon is passing through last layer
            # with partial reflectance/transmittance
            if PARTIAL_REFLECTION == 1:
                if self.layer == model.numberOfLayers \
                    and r < 1.0:
                        self.uz = uzNew # the part that is transmitted (dead)
                        self.recordReduce(model,r) # transmission through the
                            # bottom layer is seen as transmission, so the
                            # function here records transmission T
                        self.uz = -uz # the part that is reflected (alive)
                elif np.random.random() > r: # transmitted to layer+1
                    self.layer+=1
                    self.ux *= n_i/n_t
                    self.uy *= n_i/n_t
                    self.uz = uzNew
                else:
                    self.uz = -uz # internally reflected
            else:
                if np.random.random() > r:   # transmitted out
                    if self.layer == model.numberOfLayers:
                        self.uz = uzNew
                        self.recordReduce(model, 0.0)
                        self.dead = True
                    else:   # transmitted to layer+1
                        self.layer += 1
                        self.ux *= n_i/n_t
                        self.uy *= n_i/n_t
                        self.uz = uzNew
                else: 						# reflected
                    self.uz = -uz
    
    def calcFresnel(self, n1, n2, cosInc):
        """
        calculate fresnel reflectance.
        
            n1: refractive index of initial medium
            n2: refractive index of new medium
            cosInc: cosine of angle of incidence
        """
        if n1 == n2:			  	# same refractive indices
            cosTran = cosInc
            r = 0.0
        elif abs(cosInc) > COSZERO:     # nearly normal incidence 
            cosTran = cosInc
            r = (n2-n1)/(n2+n1)
            r *= r
        elif abs(cosInc) < COS90:      # nearly parallel incidence
            cosTran = 0.0
            r = 1.0
        else:           # general case	
            # sine of the incident and transmission angles
            sinInc = (1.0 - abs(cosInc)**2.0)**0.5
            sinTran = (n1/n2)*sinInc # snell's law
            if sinTran >= 1.0:
                # double check for total internal reflection
                cosTran = 0.0
                r = 1.0
            else:
                cosTran = (1.0 - sinTran**2)**0.5;  
                # trig identities for sum/difference of two angles
                # plus = inc + trans
                # minus = inc - trans     
                cosPlus = cosInc*cosTran - sinInc*sinTran     
                cosMinus = cosInc*cosTran + sinInc*sinTran     
                sinPlus = sinInc*cosTran + cosInc*sinTran     
                sinMinus = sinInc*cosTran - cosInc*sinTran     
                r = 0.5*(sinMinus**2)*(cosMinus**2 + cosPlus**2) / \
                    (sinPlus**2 * cosMinus**2)
        return r, cosTran
    
    def recordReduce(self, model, reflectance):
        """
        function to record the photon weight exiting the tissue either through
        reflection or transmission. it also updates the photon weight that
        remains in the tissue.
        
        note: photons transmitting out of the tissue through the first layer
        are viewed as reflectance in the simulation.  transmission through
        the last layer are still seen as transmittance.
        """
        x = self.x
        y = self.y
        # get indices to store weight in array
        ir = int( (x**2 + y**2)**0.5 / model.dr )
        if ir > (model.nr - 1):
            ir = (model.nr - 1)
        ia = int(np.arccos(abs(self.uz))/model.da) 
        if ia > (model.na - 1):
            ia = model.na - 1
        # function only called when photon passes through tissue surface from
        # within. if it passes through the first layer = 1, it is reflection.
        # otherwise, it must be passing through the last layer,
        # so it is transmission
        if self.layer == 1: # reflection 
            # assign dw to the reflection array in the given indices
            model.Rd_ra[ir, ia] += self.w*(1.0 - reflectance)
            # update weight
            self.w *= reflectance
        else: # transmission
            # assign dw to the transmission array in the given indices
            model.Tt_ra[ir, ia] += self.w*(1.0 - reflectance)
            # update weight
            self.w *= reflectance
            

    def hopDropSpinTissue(self, model):
        # set a step size, move the photon (hop), drop some weight (drop), 
        # and choose a new photon direction for propagation (spin).
        self.stepSizeTissue(model)
        # when a step size is long enough for the photon to 
        # hit an interface, this step is divided into two steps. 
        if self.boundaryHit(model):
            self.hop()      # first move to boundary plane
            self.newLayerCheck(model) # then determine whether
                                      # photon is reflected (or transmitted)
        # and move the photon in the current (or new)
        # medium with the remaining stepsize s_rem to interaction the
        # site.  if s_rem hits another boundary then the process is repeated
        # if photon is in muscle layer, then there is a 'cylindrical' bone 
        # passing through it along the x-axis
        # elif model.layers[self.layer].name.lower() == "muscle".lower():
        #     self.hop()
        #     if self.boneHit(model): # transmitted to bone
        #         if self.inBone(model):
        #            self.drop(model)
        #            self.spin(model.layers[self.layer].gBone) 
        #     else: # reflected back to muscle
        #         self.drop(model)
        #         self.spin(model.layers[self.layer].g)
        else:
            self.hop()
            self.drop(model)
            self.spin(model.layers[self.layer].g)
   
    def stepSizeTissue(self, model):
        layer = self.layer
        mua = model.layers[layer].mua
        mus = model.layers[layer].mus
        mut = mua + mus
        # pick a step size for a photon packet in tissue
        if self.s_rem == 0.0: # if no step remaining, make a new step
          rand = np.random.random_sample()
          self.s = -np.log(rand)/mut
        else: # otherwise, use the remaining
	        self.s = self.s_rem/mut
	        self.s_rem = 0.0    
    
    def boundaryHit(self, model):
        """
        boolean function to determine whether a photon hits a boundary or not
        """
        layer = self.layer
        z = self.z
        uz = self.uz
        mua = model.layers[layer].mua
        mus = model.layers[layer].mus
        mut = mua + mus
        if uz != 0:
            if uz > 0.0: # photon moving down
                d_b = (model.layerDepth[layer][1] - z)/uz
            else: # photon moving up
                d_b = (model.layerDepth[layer][0] - z)/uz
            if self.s > d_b: # boundary is hit
                self.s_rem = (self.s - d_b)*mut # record remaining step
                self.s = d_b # step to boundary
                hit = True
            else:
                hit = False
        return hit
    
    def boneHit(self, model):
        """
        boolean function to determine whether a photon hits bone or not
        """
        uz = self.uz
        uy = self.uy
        z = self.z
        y = self.y
        c = model.layers[self.layer].boneCenter
        r = model.layers[self.layer].rBone
        r0 = (z**2.0 + y**2.0)**0.5
        mua = model.layers[self.layer].mua
        mus = model.layers[self.layer].mus
        mut = mua + mus
        if (uz != 0):
            dz = (c[2]-z)/uz
            dy = (c[1]-y)/uy
            if (dz**2 <= (r**2.0 - dy**2.0)):
                self.z *= r/r0
                self.y *= r/r0
                self.s_rem = (r-r0)/mut
                self.s = 0
                hit = True
            else:
                hit = False
        else:
            hit = False
        return hit
    
    def inBone(self, model):
        """
        boolean function to determine whether a photon enters bone or not
        """
        uz = self.uz
        n_i = model.layers[self.layer].n # current layer
        n_t = model.layers[self.layer].nBone # new layer
        # calculate reflectance
        r, uzNew = self.calcFresnel(n_i, n_t, abs(uz))
        if np.random.random() > r: # transmitted to bone
                    self.ux *= (n_i/n_t)
                    self.uy *= (n_i/n_t)
                    inside = True
                    if uz > 0:
                        self.uz = uzNew
                    else:
                        self.uz = -uzNew
        else:
            self.uz = -uz # reflected
            inside = False
        return inside
    
# hop, drop, spin functions # FINALLY!!!!!!!!
    def hop(self):
        # move the photon
        s = self.s
        self.x += s*self.ux
        self.y += s*self.uy
        self.z += s*self.uz
    
    def drop(self, model):
        # drop weight (absorption)
        x = self.x
        y = self.y
        layer = self.layer
        if model.layers[layer].name.lower() == "muscle".lower() \
            and self.inBone(model):
                mua = model.layers[layer].muaBone
                mus = model.layers[layer].musBone
        else: 
            mua = model.layers[layer].mua
            mus = model.layers[layer].mus
        mut = mua + mus
        # get indices to store weight in absorption array A[r,z]
        iz = int(self.z/model.dz)
        if iz > (model.nz - 1):
            iz = model.nz - 1
        ir = int((x**2.0 + y**2.0)**0.5/model.dr)
        if ir > (model.nr - 1):
            ir = model.nr - 1
        # update photon weight.
        dw = self.w * mua/mut
        self.w -= dw
        # assign dw to the absorption array in the given indices
        model.A_rz[ir, iz] += dw
    
    def spin(self, g):
        """
        function used for determining the photon's new direction after 
        scattering by means of random sampling
        
            theta is the polar/deflection angle (0,pi)
            psi is the azimuthal angle (0,2pi)
        """
        ux = self.ux
        uy = self.uy
        uz = self.uz
        # determine cosine and sine of theta
        # the following formulae for computing cosine with a random
        # variable are given in the paper
        if g == 0.0: # isotropic medium
            cosTheta = 2*np.random.random() - 1
        else: # anisotropic medium
            brack = (1 - g**2)/(1 - g + 2*g*np.random.random_sample()) # brack 
                                        # is a term in brackets from the paper
                                        # it is just a placeholder to make
                                        # the code easier to read
            cosTheta = (1 + g**2 - brack**2)/(2*g)
            if cosTheta < -1:
                cosTheta = -1.0
            elif cosTheta > 1:
                cosTheta = 1.0
        sinTheta = (1.0 - cosTheta**2)**0.5
        # determine psi from random variable
        # compute cosine and sine
        psi = 2.0*np.pi*np.random.random()
        cosPsi = np.cos(psi)
        if psi < np.pi:
            sinPsi = (1.0 - cosPsi**2)**0.5
        else:
            sinPsi = -(1.0 - cosPsi**2)**0.5
        # update photon direction
        if np.fabs(uz) > COSZERO: # nearly normal incidence
            self.ux = sinTheta*cosPsi
            self.uy = sinTheta*sinPsi
            self.uz = cosTheta*np.sign(uz)
            
        else: # any other incidence
            # such terrible functions!
            self.ux = ( sinTheta*(ux*uz*cosPsi - uy*sinPsi) / \
                (1.0 - uz**2)**0.5) + ux*cosTheta
            self.uy = ( sinTheta*(uy*uz*cosPsi + ux*sinPsi) / \
                (1.0 - uz**2)**0.5) + uy*cosTheta
            self.uz = -sinTheta*cosPsi*(1.0 - uz**2)**0.5 + uz*cosTheta

   








